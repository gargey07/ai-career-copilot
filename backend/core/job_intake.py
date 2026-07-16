"""
User-submitted job intake
─────────────────────────
The "add your own job" flow: a user pastes a link, a screenshot, or raw
text of a job posting they found somewhere the pipeline doesn't reach.
This module turns that raw material into a structured job draft the user
REVIEWS AND CORRECTS before anything is stored — the same
extract → review → confirm contract as the resume-upload flow
(resume-upload-feature-spec: never auto-save what the user hasn't seen).

Responsibilities (all failure-soft — callers turn failures into friendly
"paste the text instead" guidance, never a 500):

- fetch_rendered_page_text: headless-Chromium fallback for job pages the
  plain-HTTP fetch can't read (client-rendered ATS sites). "" on failure.
- extract_text_from_image: screenshot → plain text via a vision-capable
  provider (Gemini first; text-only fallbacks are skipped, not failed).
- extract_job_draft: raw text → {title, company, location, ...} via one
  structured AI call, parsed with the same defensive JSON handling as
  core/recruiter.parse_eval. Returns (draft, failure_reason) so the API
  can distinguish "AI down, retry later" from "this content has no job
  in it, retrying won't help".
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re

from core.ai import get_ai_provider

logger = logging.getLogger(__name__)

# Job postings are short; anything past this is site chrome / boilerplate.
_MAX_INPUT_CHARS = 7000

# Below this, a fetched page almost certainly didn't contain the posting
# (login walls, JS-only shells, redirect stubs) — worth trying the rendered
# fetch before giving up.
MIN_USEFUL_PAGE_CHARS = 200

# Rendered fetch: page.goto budget, plus a hard outer cap so a wedged
# browser can never hold the intake request (or the shared Chromium lock)
# indefinitely.
_RENDER_GOTO_TIMEOUT_MS = 15_000
_RENDER_HARD_CAP_SECONDS = 30.0

EXTRACT_PROMPT = """
Below is the raw text of a job posting (it may include unrelated website
navigation or boilerplate — ignore that).

Extract the job's details. Rules:
- Use ONLY information present in the text. Missing → null.
- "description": the job's own text — responsibilities, requirements,
  qualifications — cleaned of website chrome. Keep the original wording;
  do not summarize away requirements.
- salary numbers: plain integers, no separators, null unless explicitly
  stated. "employment_type": one of full-time/part-time/contract/
  internship or null.

Respond with ONLY a JSON object, no markdown, in exactly this shape:
{{"title": "...", "company": "...", "location": "...", "description": "...", "salary_min": null, "salary_max": null, "employment_type": null, "is_remote": false}}

---

{raw_text}
"""

_IMAGE_PROMPT = (
    "This image is a screenshot of a job posting. Transcribe ALL of its "
    "text exactly as written — title, company, location, salary, "
    "requirements, description. Output plain text only, no commentary."
)


async def _rendered_page_text(url: str) -> str:
    """Body text of the page after real browser rendering."""
    from core.pdf_generator import _pdf_lock
    from playwright.async_api import async_playwright

    executable_path = os.environ.get("CHROMIUM_EXECUTABLE_PATH") or None
    # Same single-Chromium discipline as PDF generation — two headless
    # browsers at once is exactly the RAM spike that used to crash the box.
    async with _pdf_lock:
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox"], executable_path=executable_path)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=_RENDER_GOTO_TIMEOUT_MS)
                # Client-rendered ATS pages paint after domcontentloaded.
                await page.wait_for_timeout(1500)
                text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            finally:
                await browser.close()
    return re.sub(r"\s+", " ", text or "").strip()


async def fetch_rendered_page_text(url: str) -> str:
    """
    Visible text of a page rendered by headless Chromium — the fallback for
    job pages the plain-HTTP fetch (jobs/fetchers.fetch_job_page_text) can't
    read because the posting only exists after client-side JavaScript runs
    (most modern ATS sites). "" on ANY failure, same contract as the plain
    fetch — a login wall or a dead page is a normal outcome, not an error.
    """
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return ""
    try:
        return await asyncio.wait_for(_rendered_page_text(url), timeout=_RENDER_HARD_CAP_SECONDS)
    except Exception as e:
        logger.info(f"   Rendered page fetch failed for {url[:80]} ({type(e).__name__}: {e}) — treating as unreadable.")
        return ""


async def extract_text_from_image(image_bytes: bytes, mime: str) -> str | None:
    """Screenshot → plain text, or None when no vision provider succeeds."""
    try:
        ai = get_ai_provider()
        vision = getattr(ai, "generate_vision", None)
        if vision is None:
            logger.warning("   Screenshot intake: provider has no vision support.")
            return None
        text = (await vision(_IMAGE_PROMPT, image_bytes, mime) or "").strip()
        return text or None
    except Exception as e:
        logger.warning(f"   Screenshot intake failed ({e}) — user should paste text instead.")
        return None


def parse_draft(raw: str, source_text: str) -> dict | None:
    """
    Normalize the model's response into the review-screen draft, or None
    when it can't be trusted. `source_text` backstops the description —
    a draft whose description got mangled falls back to the full raw text
    the user provided, which the review screen lets them trim anyway.
    """
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    def _text(key: str, limit: int) -> str | None:
        value = str(data.get(key) or "").strip()
        return value[:limit] or None

    def _salary(key: str) -> int | None:
        try:
            value = int(data.get(key))
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None

    title = _text("title", 200)
    if not title:
        # A draft without even a title extracted is noise, not a review
        # candidate — the user is better served by the manual form.
        return None

    return {
        "title": title,
        "company": _text("company", 200),
        "location": _text("location", 200),
        "description": _text("description", 6000) or source_text[:6000],
        "salary_min": _salary("salary_min"),
        "salary_max": _salary("salary_max"),
        "employment_type": _text("employment_type", 40),
        "is_remote": bool(data.get("is_remote")),
    }


async def extract_job_draft(raw_text: str) -> tuple[dict | None, str | None]:
    """
    One AI call: raw posting text → structured draft for user review.
    Returns (draft, None) on success, or (None, reason) where reason is:
    - "ai_unavailable": every provider failed — genuinely try-again-later.
    - "no_job_found": the AI answered but couldn't find a posting in the
      text — a login wall, a redirect stub, or text that just isn't a job.
      These need DIFFERENT user messages: blaming a "busy AI" for a page
      that needs a login sends the user retrying something that can never
      work (live bug: an intapidm auth page did exactly this).
    """
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return None, "no_job_found"

    prompt = EXTRACT_PROMPT.format(raw_text=raw_text[:_MAX_INPUT_CHARS])
    try:
        ai = get_ai_provider()
        raw = await ai.generate_text(prompt, temperature=0.1)
    except Exception as e:
        logger.warning(f"   Job-draft extraction unavailable ({e}).")
        return None, "ai_unavailable"

    draft = parse_draft(raw, source_text=raw_text)
    if draft is None:
        logger.warning(f"   Job-draft extraction found no posting. Raw head: {raw[:200]!r}")
        return None, "no_job_found"
    return draft, None
