"""
PDF Resume Generator — Phase 7
────────────────────────────────────────────────────────────
Converts AI-optimized resume text → beautiful HTML → PDF using Playwright.
Stores PDFs in Supabase Storage and returns a public URL.

Flow:
  1. Fetch optimized_resume_text from user_jobs
  2. Parse plain text into structured sections
  3. Render into HTML resume template (Jinja2)
  4. Playwright renders HTML → PDF
  5. Upload PDF to Supabase Storage
  6. Update user_jobs.pdf_url + status = 'pdf_ready'

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


# ── Resume Text Parser ────────────────────────────────────────────────────────

def _parse_experience_blocks(lines: list[str]) -> list[dict]:
    """Parse experience section lines into structured blocks."""
    blocks = []
    current: Optional[dict] = None

    for line in lines:
        line = line.strip()
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
            parsed.append({"label": label.strip(), "value": value.strip()})
        elif line:
            parsed.append({"label": "", "value": line})
    return parsed


def _parse_education_blocks(lines: list[str]) -> list[dict]:
    """Parse education lines into degree/school/year blocks."""
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
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

async def generate_pdf_for_match(user_job_id: str) -> Optional[str]:
    """
    Full flow for one matched job:
      fetch data → render HTML → PDF → upload → update DB.
    Returns public PDF URL or None.
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
    if not match_resp.data or not match_resp.data.get("optimized_resume_text"):
        logger.warning(f"   ⚠️  No resume text for match {user_job_id}")
        return None

    match = match_resp.data

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
    template_name = user.get("resume_template") or "modern"
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

    # Render HTML
    html = render_resume_html(
        user_name=user.get("name", "Applicant"),
        user_email=user.get("email", ""),
        job_title=job.get("title", ""),
        company=job.get("company", ""),
        resume_text=match["optimized_resume_text"],
        template_name=template_name,
        user_location=user_location,
    )

    # Write to PDF
    short_id = user_job_id[:8]
    pdf_filename = f"resume_{short_id}.pdf"
    pdf_local_path = str(TMP_DIR / pdf_filename)

    await html_to_pdf(html, pdf_local_path)

    # Upload to Supabase Storage
    today = date.today().isoformat()
    storage_path = f"{match['user_id']}/{today}/{pdf_filename}"
    pdf_url = upload_to_supabase_storage(pdf_local_path, storage_path)

    # Update user_jobs record
    update = {"status": "pdf_ready"}
    if pdf_url:
        update["pdf_url"] = pdf_url

    supabase.table("user_jobs").update(update).eq("id", user_job_id).execute()

    # Cleanup temp file
    try:
        os.remove(pdf_local_path)
    except Exception:
        pass

    return pdf_url


async def run_pdf_generator_for_user(user_id: str) -> int:
    """
    Generate PDFs for all resume_ready matches for a user today.
    Called by the daily pipeline.
    Returns count of PDFs successfully generated.
    """
    supabase = get_supabase()
    today = date.today().isoformat()

    matches_resp = (
        supabase.table("user_jobs")
        .select("id, job_id")
        .eq("user_id", user_id)
        .eq("digest_date", today)
        .eq("status", "resume_ready")
        .execute()
    )
    matches = matches_resp.data or []

    if not matches:
        logger.info(f"   No resume_ready matches for user {user_id}")
        return 0

    logger.info(f"   Processing {len(matches)} resume(s) for PDF...")
    generated = 0
    for match in matches:
        try:
            url = await generate_pdf_for_match(match["id"])
            if url:
                logger.info(f"   ✅ PDF ready: {url[:70]}...")
                generated += 1
            else:
                logger.warning(f"   ⚠️  PDF generated but no storage URL for {match['id']}")
                generated += 1  # still count as generated (local)
        except Exception as e:
            logger.error(f"   ❌ PDF failed for match {match['id']}: {e}")

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
