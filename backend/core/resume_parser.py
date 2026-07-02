"""
Resume Parser — Text Extraction + AI-Structured Extraction
─────────────────────────────────────────────────────────
Pulls raw text out of an uploaded PDF/DOCX and asks the AI provider to
turn it into the structured profile shape used across onboarding (the
resume review screen and manual "start from scratch" entry both save
into this same shape — see EMPTY_PROFILE below).
"""
from __future__ import annotations
import json
import logging
import re
from io import BytesIO

import pdfplumber
from docx import Document

from core.ai import get_ai_provider
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)

RESUME_UPLOADS_BUCKET = "resume-uploads"
MIN_EXTRACTED_TEXT_LENGTH = 50  # shorter than this = likely a scanned/image-only PDF
MAX_PROMPT_CHARS = 15000        # keeps the prompt within a safe context/cost budget

EMPTY_PROFILE = {
    "basic_info": {"full_name": "", "email": "", "phone": "", "location": ""},
    "summary": "",
    "work_experience": [],
    "projects": [],
    "education": [],
    "target_roles": [],
    "skills": [],
    "tools": [],
    "links": {"linkedin": "", "portfolio": "", "github": ""},
    "confidence_flags": {},
}

EXTRACTION_PROMPT = """You are extracting structured data from a resume. Read the resume text below and
return ONLY valid JSON (no markdown, no commentary, no code fences) matching exactly this shape:

{{
  "basic_info": {{"full_name": "", "email": "", "phone": "", "location": ""}},
  "summary": "",
  "work_experience": [{{"title": "", "company": "", "start_date": "", "end_date": "", "is_current": false, "bullets": [""]}}],
  "projects": [{{"name": "", "project_type": "personal", "role": "", "description": "", "technologies": [""], "url": "", "github": ""}}],
  "education": [{{"school": "", "degree": "", "field_of_study": "", "start_date": "", "end_date": ""}}],
  "target_roles": [""],
  "skills": [""],
  "tools": [""],
  "links": {{"linkedin": "", "portfolio": "", "github": ""}},
  "confidence_flags": {{}}
}}

Rules:
- "target_roles" = job titles this person is qualified for based on their experience (best guess, 1-4 roles).
- "skills" = soft/hard competencies (e.g. "REST API Design", "User Research"). "tools" = named software/technologies/languages (e.g. "Figma", "Python").
- "work_experience" = professional employment only (full-time, part-time, internships, paid freelance engagements).
- "projects" = personal, academic, capstone, research, open-source, or portfolio work that is NOT employment. If the resume has a Projects section, or an item has no employer/salary context, it belongs here — never in work_experience. "project_type" is one of: personal, academic, freelance, research, open_source, capstone.
- Dates as free text are fine (e.g. "Jan 2022", "2022", "Present").
- "is_current" is true if the role is ongoing.
- Add an entry to "confidence_flags" for any top-level field you could not find or are unsure about, e.g. {{"phone": "missing"}} or {{"summary": "low_confidence"}}. Omit fields you're confident about.
- If you cannot find a value, use "" (or [] for lists) — never invent data.

Resume text:
---
{resume_text}
---

Return only the JSON object.
"""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from a PDF file's bytes."""
    text_parts = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts).strip()


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract raw text from a DOCX file's bytes."""
    doc = Document(BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text).strip()


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Dispatch to the right extractor based on file extension."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    if ext == "docx":
        return extract_text_from_docx(file_bytes)
    raise ValueError(f"Unsupported file type: .{ext}")


def is_text_too_short(text: str) -> bool:
    """Heuristic for scanned/image-only PDFs with no extractable text layer."""
    return len(text.strip()) < MIN_EXTRACTED_TEXT_LENGTH


def _strip_json_fences(text: str) -> str:
    """Gemini sometimes wraps JSON in ```json ... ``` despite instructions not to — strip it."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def parse_resume_text(resume_text: str) -> dict:
    """
    Sends resume text to the AI provider and returns structured profile
    data matching EMPTY_PROFILE's shape. Retries once on malformed JSON,
    then falls back to an empty profile rather than raising — a blank
    review form beats a crashed onboarding flow.
    """
    ai = get_ai_provider()
    prompt = EXTRACTION_PROMPT.format(resume_text=resume_text[:MAX_PROMPT_CHARS])

    for attempt in range(2):
        try:
            raw = await ai.generate_text(prompt, temperature=0.1)
            parsed = json.loads(_strip_json_fences(raw))
            return {**EMPTY_PROFILE, **parsed}  # ensure every expected key exists
        except json.JSONDecodeError as e:
            logger.warning(f"   ⚠️  Gemini returned malformed JSON (attempt {attempt + 1}): {e}")
            prompt = "Your last response was not valid JSON. Return ONLY the JSON object, nothing else.\n\n" + prompt
        except Exception as e:
            logger.error(f"   ❌ Resume extraction failed: {e}")
            break

    logger.warning("   ⚠️  Falling back to empty profile after failed extraction")
    return dict(EMPTY_PROFILE)


def upload_resume_file(file_bytes: bytes, storage_path: str, content_type: str) -> str:
    """
    Uploads a raw resume file to the PRIVATE 'resume-uploads' bucket.
    Returns the storage path (not a public URL — this bucket is private,
    contains PII, and is only ever read by the backend's service_role key).
    """
    supabase = get_supabase()

    try:
        supabase.storage.create_bucket(RESUME_UPLOADS_BUCKET, options={"public": False})
        logger.info(f"   Created storage bucket: {RESUME_UPLOADS_BUCKET}")
    except Exception:
        pass

    supabase.storage.from_(RESUME_UPLOADS_BUCKET).upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return storage_path


def build_resume_text_from_profile(profile: dict) -> str:
    """
    Flattens the structured profile into a plain-text resume string,
    kept in sync on every save so the existing matching/optimization
    pipeline (core/matcher.py, core/optimizer.py) — which expects a
    single resume_text blob — needs no changes.
    """
    basic = profile.get("basic_info", {}) or {}
    lines = [basic.get("full_name", ""), profile.get("summary", ""), "", "EXPERIENCE"]

    for job in profile.get("work_experience", []) or []:
        end = "Present" if job.get("is_current") else job.get("end_date", "")
        lines.append(f"{job.get('title', '')} — {job.get('company', '')} ({job.get('start_date', '')} - {end})")
        for bullet in job.get("bullets", []) or []:
            if bullet:
                lines.append(f"• {bullet}")

    projects = profile.get("projects", []) or []
    if projects:
        # Projects are one of the strongest matching signals (see
        # docs/AI_CAREER_INTELLIGENCE_ENGINE.md) — always in the text blob.
        lines += ["", "PROJECTS"]
        for proj in projects:
            header = proj.get("name", "")
            if proj.get("role"):
                header += f" — {proj['role']}"
            techs = ", ".join(proj.get("technologies", []) or [])
            if techs:
                header += f" ({techs})"
            lines.append(header)
            if proj.get("description"):
                lines.append(f"• {proj['description']}")

    lines += ["", "EDUCATION"]
    for edu in profile.get("education", []) or []:
        lines.append(
            f"{edu.get('degree', '')} {edu.get('field_of_study', '')} — "
            f"{edu.get('school', '')} ({edu.get('start_date', '')} - {edu.get('end_date', '')})"
        )

    skills = profile.get("skills", []) or []
    tools = profile.get("tools", []) or []
    if skills or tools:
        lines += ["", "SKILLS", ", ".join([*tools, *skills])]

    return "\n".join(line for line in lines if line is not None).strip()
