"""
PDF Resume Generator — Phase 7
────────────────────────────────────────────────────────────
Converts AI-optimized resume text → beautiful HTML → PDF using Playwright.
Stores PDFs in Supabase Storage and returns a public URL.

Flow:
  1. Fetch optimized_resume_text from user_jobs
  2. Parse plain text into structured sections
  3. Render into HTML resume template (Jinja2)
  4. Playwright renders HTML → PDF (60s timeout, one at a time process-wide)
  5. Upload PDF to Supabase Storage
  6. Update user_jobs.pdf_url + status = 'pdf_ready' — or, on any failure,
     status = 'pdf_failed' + pdf_error_message (never left stuck)

Run standalone:
    PYTHONPATH=. python3 core/pdf_generator.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

from core.config import get_settings
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
TMP_DIR = Path(__file__).parent.parent / "tmp"

# A Chromium render that never finishes must not leave a match stuck
# forever — cap it and always resolve to pdf_ready or pdf_failed.
PDF_GENERATION_TIMEOUT_SECONDS = 60

# Render's free tier is a single 0.1-CPU / 512MB instance running one
# uvicorn worker (see render.yaml — no --workers flag). This in-process
# lock is therefore sufficient (not distributed) to stop the nightly
# pipeline and an instant-first-match background task from launching two
# Chromium processes at once and OOM-killing the instance.
_pdf_lock = asyncio.Lock()


# ── Resume Text Parser ────────────────────────────────────────────────────────

# The AI is told never to write placeholder dates, but older stored resumes
# (and occasional model slips) contain literal "( - )" / "(-)" artifacts
# where the original resume had no dates. Strip them rather than printing
# them on the final PDF.
_EMPTY_PARENS_RE = re.compile(r'\(\s*[-–—]?\s*\)')


def _strip_empty_parens(text: str) -> str:
    return _EMPTY_PARENS_RE.sub('', text).strip()


def _parse_pipe_experience(lines: list[str]) -> list[dict]:
    """
    Parse the strict pipe format the optimizer prompt now requests:
        Job Title | Company | Dates
        - bullet
    Returns [] if no pipe headers found (caller falls back to heuristics).
    """
    blocks: list[dict] = []
    current: Optional[dict] = None
    for line in lines:
        line = _strip_empty_parens(line.strip())
        if not line:
            continue
        if "|" in line and not line.startswith(("-", "•", "▸", "*")):
            if current:
                blocks.append(current)
            parts = [p.strip() for p in line.split("|")]
            current = {
                "title": parts[0] if parts else "",
                "company": parts[1] if len(parts) > 1 else "",
                "dates": parts[2] if len(parts) > 2 else "",
                "bullets": [],
            }
        elif line.startswith(("-", "•", "▸", "*")) and current:
            bullet = re.sub(r'^[-•▸\*]\s*', '', line).strip()
            if bullet:
                current["bullets"].append(bullet)
        elif current and not current["bullets"] and not current["company"]:
            current["company"] = line
    if current:
        blocks.append(current)
    return blocks if any(b["title"] for b in blocks) else []


def _parse_experience_blocks(lines: list[str]) -> list[dict]:
    """Parse experience section lines into structured blocks."""
    # Strict pipe format first (what the optimizer prompt now requests) —
    # far more reliable than the header-shape heuristics below, which
    # mis-split titles/companies on free-form AI output.
    pipe_blocks = _parse_pipe_experience(lines)
    if pipe_blocks:
        return pipe_blocks

    blocks = []
    current: Optional[dict] = None

    for line in lines:
        line = _strip_empty_parens(line.strip())
        if not line:
            continue

        # Detect role header: "Title — Company, Location  (dates)"
        if re.match(r'^[A-Z][^•\-]{5,}(—|-–|–)\s*.+', line) or (
            len(line) < 80 and not line.startswith("•") and not line.startswith("-")
            and not line.startswith("▸") and "  " in line
        ):
            if current:
                blocks.append(current)
            # Try to extract dates
            dates_match = re.search(r'\((.+?)\)\s*$', line)
            dates = dates_match.group(1) if dates_match else ""
            clean_line = re.sub(r'\s*\(.+?\)\s*$', '', line).strip()

            # Split on — or –
            parts = re.split(r'\s*[—–-]{1,2}\s*', clean_line, maxsplit=1)
            title = parts[0].strip()
            company = parts[1].strip() if len(parts) > 1 else ""

            current = {"title": title, "company": company, "dates": dates, "bullets": []}

        elif line.startswith(("•", "-", "▸", "*")) and current:
            bullet = re.sub(r'^[•\-▸\*]\s*', '', line).strip()
            if bullet:
                current["bullets"].append(bullet)

        elif current and current.get("title") and not current.get("company"):
            # Second line might be the company/location line
            if not line.startswith(("•", "-", "▸")):
                current["company"] = line

    if current:
        blocks.append(current)

    return blocks


def _parse_skills(lines: list[str]) -> list[dict]:
    """Parse skills lines into label: value pairs."""
    parsed = []
    for line in lines:
        line = line.strip()
        if ":" in line:
            label, _, value = line.partition(":")
            label, value = label.strip(), value.strip()
            # A line starting with ":" produces an empty label and rendered
            # as a dangling "‌: Figma, ..." on the PDF — treat as unlabeled.
            if not value:
                label, value = "", label
            parsed.append({"label": label, "value": value})
        elif line:
            parsed.append({"label": "", "value": line})
    return parsed


def _parse_education_blocks(lines: list[str]) -> list[dict]:
    """Parse education lines into degree/school/year blocks."""
    blocks = []
    i = 0
    while i < len(lines):
        line = _strip_empty_parens(lines[i].strip())
        if not line:
            i += 1
            continue

        # Strict pipe format first: "Degree | School | Year"
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            blocks.append({
                "degree": parts[0] if parts else "",
                "school": parts[1] if len(parts) > 1 else "",
                "year": parts[2] if len(parts) > 2 else "",
            })
            i += 1
            continue

        # Try to extract year
        year_match = re.search(r'\((\d{4}[\-–]\d{4}|\d{4})\)', line)
        year = year_match.group(1) if year_match else ""
        clean = re.sub(r'\s*\(\d{4}[\-–]?\d{0,4}\)\s*$', '', line).strip()

        # Split on — to get degree vs school
        parts = re.split(r'\s*[—–-]{1,2}\s*', clean, maxsplit=1)
        degree = parts[0].strip()
        school = parts[1].strip() if len(parts) > 1 else ""

        # Free-form AI output sometimes duplicates the degree into the
        # school half ("M. UI/UX Design — UI/UX Design") — drop the echo
        # when the "school" is really just (part of) the degree again.
        if school and school.lower() in degree.lower():
            school = ""

        blocks.append({"degree": degree, "school": school, "year": year})
        i += 1

    return blocks


def parse_resume_sections(resume_text: str) -> dict:
    """
    Parse AI optimizer output (plain text with section headers) into
    a structured dict for the HTML template.
    """
    section_headers = {
        "SUMMARY": "summary",
        "PROFESSIONAL SUMMARY": "summary",
        "PROFESSIONAL EXPERIENCE": "experience",
        "EXPERIENCE": "experience",
        "WORK EXPERIENCE": "experience",
        "SKILLS": "skills",
        "EDUCATION": "education",
    }

    result = {
        "summary": "",
        "experience_lines": [],
        "skills_lines": [],
        "education_lines": [],
    }

    current_section = None
    current_lines: list[str] = []

    def flush():
        nonlocal current_lines
        if current_section == "summary":
            result["summary"] = " ".join(l for l in current_lines if l.strip())
        elif current_section == "experience":
            result["experience_lines"] = [l for l in current_lines if l.strip()]
        elif current_section == "skills":
            result["skills_lines"] = [l for l in current_lines if l.strip()]
        elif current_section == "education":
            result["education_lines"] = [l for l in current_lines if l.strip()]
        current_lines = []

    for line in resume_text.split("\n"):
        upper = line.strip().upper().rstrip(":")
        matched = section_headers.get(upper)
        if matched:
            flush()
            current_section = matched
        else:
            current_lines.append(line)

    flush()

    # Build structured data
    exp_blocks = _parse_experience_blocks(result["experience_lines"])
    skills_parsed = _parse_skills(result["skills_lines"])
    edu_blocks = _parse_education_blocks(result["education_lines"])

    return {
        "summary": result["summary"],
        # Structured (preferred)
        "experience_blocks": exp_blocks if exp_blocks else None,
        "skills_parsed": skills_parsed if skills_parsed else None,
        "education_blocks": edu_blocks if edu_blocks else None,
        # Raw fallback if parsing fails
        "experience_raw": "\n".join(result["experience_lines"]) if not exp_blocks else None,
        "skills_raw": "\n".join(result["skills_lines"]) if not skills_parsed else None,
        "education_raw": "\n".join(result["education_lines"]) if not edu_blocks else None,
    }


# ── HTML Rendering ────────────────────────────────────────────────────────────

def render_resume_html(
    user_name: str,
    user_email: str,
    job_title: str,
    company: str,
    resume_text: str,
    template_name: str = "modern",
    target_role: str = "",
    user_location: str = "",
) -> str:
    """Render resume text into a beautiful HTML page using a Jinja2 template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template(f"resume_{template_name}.html")

    sections = parse_resume_sections(resume_text)

    return template.render(
        user_name=user_name,
        user_email=user_email,
        job_title=job_title,
        company=company,
        target_role=target_role or job_title,
        user_location=user_location,
        today=date.today().strftime("%B %d, %Y"),
        **sections,
    )


# ── PDF Rendering ─────────────────────────────────────────────────────────────

async def html_to_pdf(html_content: str, output_path: str) -> int:
    """
    Render HTML to PDF using Playwright headless Chromium.
    Returns file size in bytes.
    """
    TMP_DIR.mkdir(exist_ok=True)

    # Normally Playwright uses its own downloaded Chromium (installed at
    # build time — see render.yaml). CHROMIUM_EXECUTABLE_PATH overrides it
    # for hosts where a system Chromium already exists.
    executable_path = os.environ.get("CHROMIUM_EXECUTABLE_PATH") or None

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"], executable_path=executable_path)
        page = await browser.new_page()

        await page.set_content(html_content, wait_until="domcontentloaded")
        # Short wait for fonts/CSS to apply
        await page.wait_for_timeout(500)

        await page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={"top": "0mm", "bottom": "10mm", "left": "0mm", "right": "0mm"},
        )
        await browser.close()

    size = os.path.getsize(output_path)
    logger.info(f"   PDF rendered: {output_path} ({size:,} bytes)")
    return size


# ── Supabase Storage Upload ───────────────────────────────────────────────────

def upload_to_supabase_storage(pdf_path: str, storage_path: str) -> Optional[str]:
    """
    Upload PDF to Supabase Storage (bucket: 'resumes').
    Returns the public URL or None on failure.
    """
    supabase = get_supabase()
    bucket = "resumes"

    # Ensure bucket exists (silently ignore if already there)
    try:
        supabase.storage.create_bucket(bucket, options={"public": True})
        logger.info(f"   Created storage bucket: {bucket}")
    except Exception:
        pass

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    try:
        supabase.storage.from_(bucket).upload(
            path=storage_path,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
        url = supabase.storage.from_(bucket).get_public_url(storage_path)
        logger.info(f"   Uploaded to storage: {storage_path}")
        return url
    except Exception as e:
        logger.error(f"   ❌ Storage upload failed: {e}")
        return None


# ── Main Pipeline Function ────────────────────────────────────────────────────

def _resume_is_effectively_empty(sections: dict) -> bool:
    """
    TICKET-009 quality check: if the AI returned essentially nothing (every
    section blank — summary, experience, skills, education), rendering a
    PDF just produces a broken/blank resume. Catch it before wasting a
    Chromium render, and surface it as a failure the user can retry.
    """
    return not any([
        (sections.get("summary") or "").strip(),
        sections.get("experience_blocks") or (sections.get("experience_raw") or "").strip(),
        sections.get("skills_parsed") or (sections.get("skills_raw") or "").strip(),
        sections.get("education_blocks") or (sections.get("education_raw") or "").strip(),
    ])


def _mark_pdf_failed(supabase, user_job_id: str, error_message: str) -> None:
    try:
        supabase.table("user_jobs").update({
            "status": "pdf_failed",
            "pdf_error_message": error_message[:500],
        }).eq("id", user_job_id).execute()
    except Exception as e:
        logger.error(f"   Couldn't record pdf_failed status for {user_job_id} either: {e}")


async def generate_pdf_for_match(user_job_id: str) -> Optional[str]:
    """
    Full flow for one matched job:
      fetch data → render HTML → PDF → upload → update DB.
    Returns public PDF URL or None.

    Every failure mode (empty AI output, Chromium crash/timeout, storage
    upload failure) resolves the match to status='pdf_failed' with a
    reason in pdf_error_message — never leaves it stuck looking like it's
    still generating. Not selected for AI treatment at all (no
    optimized_resume_text yet) is a different, non-error case and leaves
    the row untouched.
    """
    supabase = get_supabase()

    # Fetch match + resume text
    match_resp = (
        supabase.table("user_jobs")
        .select("id, user_id, job_id, optimized_resume_text")
        .eq("id", user_job_id)
        .single()
        .execute()
    )
    if not match_resp.data:
        logger.warning(f"   ⚠️  Match {user_job_id} not found")
        return None

    match = match_resp.data
    resume_text = match.get("optimized_resume_text")

    # None = the optimizer never got to this match (not selected for AI
    # tailoring this cycle — normal, not an error). "" (explicitly empty,
    # as opposed to missing) means the AI ran but produced nothing — that
    # IS a failure, distinct from "not attempted", so it must not be
    # silently swallowed by the same early-return.
    if resume_text is None:
        logger.warning(f"   ⚠️  No resume text for match {user_job_id} — not yet selected for AI tailoring, not a failure")
        return None
    if not resume_text.strip():
        _mark_pdf_failed(supabase, user_job_id, "AI-generated resume text was empty — nothing to render.")
        return None

    # Fetch user
    user_resp = (
        supabase.table("users")
        .select("name, email, preferred_locations, resume_template")
        .eq("id", match["user_id"])
        .single()
        .execute()
    )
    user = user_resp.data or {}
    locations = user.get("preferred_locations") or []
    user_location = locations[0] if locations else ""

    # User-chosen resume design (modern | classic | minimal). Guard against
    # bad/legacy values — a missing template must not kill PDF generation.
    template_name = user.get("resume_template") or "professional"
    if not (TEMPLATES_DIR / f"resume_{template_name}.html").exists():
        template_name = "modern"

    # Fetch job
    job_resp = (
        supabase.table("jobs")
        .select("title, company")
        .eq("id", match["job_id"])
        .single()
        .execute()
    )
    job = job_resp.data or {}

    logger.info(f"   📄 Generating PDF: {job.get('title')} @ {job.get('company')}")

    short_id = user_job_id[:8]
    pdf_filename = f"resume_{short_id}.pdf"
    pdf_local_path = str(TMP_DIR / pdf_filename)

    try:
        # Non-empty text can still parse down to nothing usable (e.g. junk
        # section headers with no real content) — catch that too, not just
        # the literal-empty-string case handled above.
        sections = parse_resume_sections(resume_text)
        if _resume_is_effectively_empty(sections):
            raise ValueError("AI-generated resume text had no usable content.")

        html = render_resume_html(
            user_name=user.get("name", "Applicant"),
            user_email=user.get("email", ""),
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            resume_text=resume_text,
            template_name=template_name,
            user_location=user_location,
        )

        async with _pdf_lock:
            await asyncio.wait_for(html_to_pdf(html, pdf_local_path), timeout=PDF_GENERATION_TIMEOUT_SECONDS)

        today = date.today().isoformat()
        storage_path = f"{match['user_id']}/{today}/{pdf_filename}"
        pdf_url = upload_to_supabase_storage(pdf_local_path, storage_path)
        if not pdf_url:
            raise RuntimeError("PDF rendered but the upload to storage failed.")

        supabase.table("user_jobs").update({
            "status": "pdf_ready",
            "pdf_url": pdf_url,
            "pdf_error_message": None,
        }).eq("id", user_job_id).execute()
        return pdf_url

    except asyncio.TimeoutError:
        error_message = f"Timed out after {PDF_GENERATION_TIMEOUT_SECONDS}s rendering the PDF."
        logger.error(f"   ❌ {error_message} (match {user_job_id})")
        _mark_pdf_failed(supabase, user_job_id, error_message)
        return None
    except Exception as e:
        logger.error(f"   ❌ PDF generation failed for match {user_job_id}: {e}")
        _mark_pdf_failed(supabase, user_job_id, str(e))
        return None
    finally:
        try:
            os.remove(pdf_local_path)
        except FileNotFoundError:
            pass
        except Exception:
            pass


async def run_pdf_generator_for_user(user_id: str) -> int:
    """
    Generate PDFs for all resume_ready matches for a user today.
    Called by the daily pipeline.
    Returns count of PDFs successfully generated.
    """
    supabase = get_supabase()
    today = date.today().isoformat()

    # Select by WORK REMAINING (has resume text, no PDF yet), not by
    # status — the digest email flips matches to 'emailed', which used to
    # lock them out of PDF generation the same way it locked them out of
    # the optimizer. 'pdf_failed' is excluded: those retry only through
    # the user-facing Retry button (see api/routes/users.py retry-pdf).
    matches_resp = (
        supabase.table("user_jobs")
        .select("id, job_id")
        .eq("user_id", user_id)
        .eq("digest_date", today)
        .not_.is_("optimized_resume_text", "null")
        .is_("pdf_url", "null")
        .neq("status", "pdf_failed")
        .execute()
    )
    matches = matches_resp.data or []

    if not matches:
        logger.info(f"   No matches awaiting PDF generation for user {user_id}")
        return 0

    logger.info(f"   Processing {len(matches)} resume(s) for PDF...")
    generated = 0
    for match in matches:
        # generate_pdf_for_match handles its own failures internally (always
        # resolves the row to pdf_ready/pdf_failed) — this try/except is
        # just defense in depth, not the primary error path.
        try:
            url = await generate_pdf_for_match(match["id"])
            if url:
                logger.info(f"   ✅ PDF ready: {url[:70]}...")
                generated += 1
            else:
                logger.warning(f"   ⚠️  PDF not generated for {match['id']} — check pdf_error_message on the row")
        except Exception as e:
            logger.error(f"   ❌ Unexpected error generating PDF for match {match['id']}: {e}")

    return generated


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    # Test with a real user_job_id from your Supabase user_jobs table
    # Get it from: SELECT id FROM user_jobs WHERE status = 'resume_ready' LIMIT 1;
    supabase = get_supabase()
    today = date.today().isoformat()

    matches = (
        supabase.table("user_jobs")
        .select("id, job_id")
        .eq("digest_date", today)
        .eq("status", "resume_ready")
        .limit(1)
        .execute()
    ).data

    if not matches:
        print("❌ No resume_ready matches found for today.")
        print("   Run the pipeline first: python3 pipeline.py --test")
    else:
        match_id = matches[0]["id"]
        print(f"Testing PDF generation for match: {match_id}")
        url = asyncio.run(generate_pdf_for_match(match_id))
        print(f"\n✅ PDF URL: {url}" if url else "\n⚠️  No URL returned (check logs)")
