"""
Resume Upload / Parse / Confirm API
──────────────────────────────────
Upload flow: POST /upload or /upload-url returns a job_id immediately
and parses in a FastAPI BackgroundTasks task (not a blocking request —
Render's free tier is a single 0.1-CPU worker, and a synchronous
5-15s Gemini call would stall every other request). The frontend polls
GET /parse-status/{job_id} until it's done, then a user reviews/edits
the result and POSTs the final shape to /confirm, which is also how
the no-resume "start from scratch" path saves a profile.
"""
from __future__ import annotations
import logging
from typing import Optional
from urllib.parse import urlparse
import re
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from core.config import get_settings
from core.resume_parser import (
    build_resume_text_from_profile,
    extract_text,
    is_text_too_short,
    parse_resume_text,
    upload_resume_file,
)
from core.usage_guard import check_budget
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB
RESUME_TEMPLATES = {"modern", "classic", "minimal"}  # backend/templates/resume_<name>.html
_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ── Request/response models ───────────────────────────────────────────────────
class UploadUrlRequest(BaseModel):
    url: str


class ExperienceEntry(BaseModel):
    title: str = ""
    company: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    bullets: list[str] = []


class ProjectEntry(BaseModel):
    # Projects are NOT work experience — own section, own shape
    # (docs/PRODUCT_STRATEGY_BETA.md). project_type: personal | academic |
    # freelance | research | open_source | capstone.
    name: str = ""
    project_type: str = "personal"
    role: str = ""
    description: str = ""
    technologies: list[str] = []
    url: str = ""
    github: str = ""


class EducationEntry(BaseModel):
    school: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""


class Links(BaseModel):
    linkedin: str = ""
    portfolio: str = ""
    github: str = ""


class BasicInfo(BaseModel):
    full_name: str = ""
    email: str
    phone: str = ""
    location: str = ""


class ConfirmProfileRequest(BaseModel):
    basic_info: BasicInfo
    summary: str = ""
    work_experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    links: Links = Field(default_factory=Links)
    confidence_flags: dict = Field(default_factory=dict)

    # Onboarding-specific fields — not part of the parsed-resume shape,
    # but collected on the same review screen.
    job_category: str = ""
    experience_level: str = "mid"
    preferred_locations: list[str] = Field(default_factory=list)
    work_type: list[str] = Field(default_factory=list)
    resume_file_path: Optional[str] = None  # set if this profile came from an uploaded resume
    resume_template: str = "modern"  # which PDF design their tailored resumes use


# ── Helpers ────────────────────────────────────────────────────────────────────
def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sniff_extension(content: bytes) -> Optional[str]:
    """Real file-type check via magic bytes — never trust a claimed extension alone."""
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"PK\x03\x04"):  # DOCX is a zip archive
        return "docx"
    return None


def _validate_and_get_extension(content: bytes, claimed_filename: str) -> str:
    claimed_ext = claimed_filename.lower().rsplit(".", 1)[-1] if "." in claimed_filename else ""
    sniffed_ext = _sniff_extension(content)

    if sniffed_ext is None:
        raise HTTPException(400, "File doesn't look like a valid PDF or DOCX.")
    if claimed_ext and claimed_ext != sniffed_ext:
        raise HTTPException(
            400, f"File extension (.{claimed_ext}) doesn't match its actual contents (looks like .{sniffed_ext})."
        )
    return sniffed_ext


def _normalize_share_url(url: str) -> str:
    """
    Convert common cloud "share" links (which serve an HTML viewer page, not
    the file) into direct-download URLs so the PDF/DOCX bytes come through.
    """
    # Google Drive: /file/d/<id>/... or ?id=<id>  ->  uc?export=download&id=<id>
    m = re.search(r"drive\.google\.com/file/d/([A-Za-z0-9_-]+)", url)
    if not m:
        m = re.search(r"drive\.google\.com/(?:open|uc)\?[^ ]*\bid=([A-Za-z0-9_-]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"

    # Dropbox: force direct download
    if "dropbox.com" in url:
        return re.sub(r"([?&])dl=0", r"\1dl=1", url) if "dl=" in url else url + ("&dl=1" if "?" in url else "?dl=1")

    return url


async def _download_url(url: str, max_bytes: int) -> tuple[bytes, str]:
    """Streams a URL server-side, aborting early past max_bytes. Returns (content, hinted filename)."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"File exceeds {max_bytes // (1024 * 1024)}MB limit.")
                chunks.append(chunk)

            filename = ""
            cd_match = re.search(r'filename="?([^";]+)"?', resp.headers.get("content-disposition", ""))
            if cd_match:
                filename = cd_match.group(1)
            if not filename:
                filename = urlparse(url).path.rsplit("/", 1)[-1]

            return b"".join(chunks), filename


def _create_parse_job(source: str, file_path: Optional[str]) -> dict:
    supabase = get_supabase()
    resp = supabase.table("resume_parse_jobs").insert(
        {"source": source, "file_path": file_path, "status": "pending"}
    ).execute()
    return resp.data[0]


async def _process_parse_job(job_id: str, content: bytes, filename: str) -> None:
    """Runs in the background after the upload response has already been sent."""
    supabase = get_supabase()
    try:
        supabase.table("resume_parse_jobs").update({"status": "processing"}).eq("id", job_id).execute()

        text = extract_text(content, filename)
        if is_text_too_short(text):
            supabase.table("resume_parse_jobs").update({
                "status": "failed",
                "error_message": (
                    "This looks like a scanned image with no extractable text — "
                    "try a text-based PDF, or fill in your info manually."
                ),
            }).eq("id", job_id).execute()
            return

        profile = await parse_resume_text(text)
        supabase.table("resume_parse_jobs").update({"status": "done", "result": profile}).eq("id", job_id).execute()

    except Exception as e:
        logger.error(f"   ❌ Resume parse job {job_id} failed: {e}")
        try:
            supabase.table("resume_parse_jobs").update({
                "status": "failed",
                "error_message": "Something went wrong parsing your resume. Try again or fill in manually.",
            }).eq("id", job_id).execute()
        except Exception:
            pass  # DB itself may be unreachable — nothing more we can do


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post("/upload", status_code=202)
async def upload_resume(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.")

    extension = _validate_and_get_extension(content, file.filename or "")

    client_ip = _client_ip(request)
    if not check_budget(f"resume_parse_ip_{client_ip}", settings.resume_parse_daily_limit_per_ip):
        raise HTTPException(429, "Too many resume uploads today. Please try again tomorrow.")

    storage_path = f"{uuid4()}.{extension}"
    upload_resume_file(content, storage_path, _CONTENT_TYPES[extension])

    job = _create_parse_job(source="file", file_path=storage_path)
    background_tasks.add_task(_process_parse_job, job["id"], content, f"resume.{extension}")

    return {"job_id": job["id"], "status": "pending"}


@router.post("/upload-url", status_code=202)
async def upload_resume_from_url(payload: UploadUrlRequest, request: Request, background_tasks: BackgroundTasks):
    if not payload.url.startswith(("http://", "https://")):
        raise HTTPException(400, "Please provide a valid http(s) URL.")

    client_ip = _client_ip(request)
    if not check_budget(f"resume_parse_ip_{client_ip}", settings.resume_parse_daily_limit_per_ip):
        raise HTTPException(429, "Too many resume uploads today. Please try again tomorrow.")

    download_url = _normalize_share_url(payload.url)
    try:
        content, _hinted_filename = await _download_url(download_url, MAX_UPLOAD_BYTES)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(400, f"Couldn't download that URL: {e}")

    extension = _sniff_extension(content)
    if extension is None:
        raise HTTPException(
            400,
            "That link didn't return a PDF or DOCX file. Make sure it points directly at the "
            "file and is shared publicly (Google Drive / Dropbox share links work; private or "
            "preview-only links don't). You can also upload the file directly or fill in manually.",
        )

    storage_path = f"{uuid4()}.{extension}"
    upload_resume_file(content, storage_path, _CONTENT_TYPES[extension])

    job = _create_parse_job(source="url", file_path=storage_path)
    background_tasks.add_task(_process_parse_job, job["id"], content, f"resume.{extension}")

    return {"job_id": job["id"], "status": "pending"}


@router.get("/parse-status/{job_id}")
async def get_parse_status(job_id: str):
    supabase = get_supabase()
    resp = supabase.table("resume_parse_jobs").select("status, result, error_message, file_path").eq("id", job_id).execute()
    if not resp.data:
        raise HTTPException(404, "Parse job not found.")
    return resp.data[0]


async def _match_new_user(user_id: str) -> None:
    """
    Instant first match — a core journey step (docs/PRODUCT_STRATEGY_BETA.md):
    signup must end with real matches AND resumes on the dashboard, not
    "come back tomorrow". Runs after the confirm response is sent; uses
    the same matcher as the nightly pipeline (vector when available,
    keyword fallback otherwise), then immediately tries to generate
    tailored resumes for the top matches too — previously this only
    matched jobs, so "Resumes Ready" sat at 0 until the next scheduled
    pipeline run. No email here (that's still the nightly digest's job;
    sending one immediately on signup would be a second, redundant send).
    Best-effort throughout: an empty job pool or AI budget cap just means
    fewer/no matches or resumes, never a failed signup.
    """
    # Fetch jobs for THIS user's category first. The shared pool only
    # contains categories of existing users' past fetches, and matching now
    # enforces category relevance instead of padding with other categories'
    # jobs — so a signup in a never-fetched category (the first fullstack
    # dev, the first marketer...) would otherwise land on an honest-but-
    # empty dashboard until the next morning's pipeline. Best-effort and
    # budget-guarded like every fetch; a failure just means matching runs
    # against whatever pool already exists.
    try:
        from database.supabase_client import get_supabase
        from jobs.fetchers import run_all_fetchers
        from core.pipeline_runner import _queries_for_category

        user_resp = get_supabase().table("users").select("job_category").eq("id", user_id).single().execute()
        category = ((user_resp.data or {}).get("job_category") or "").strip()
        if category:
            for query in _queries_for_category(category)[:1]:  # one query — signup latency matters
                fetched = await run_all_fetchers(query=query, category=category)
                logger.info(f"⚡ Signup fetch for '{category}': {fetched} new jobs")
    except Exception as e:
        logger.warning(f"⚠️  Signup-time job fetch failed for {user_id}: {e}")

    try:
        from core.matcher import match_jobs_for_user, store_matches

        matches = await match_jobs_for_user(user_id)
        stored = await store_matches(user_id, matches)
        logger.info(f"⚡ Instant first match for {user_id}: {stored} matches stored")
    except Exception as e:
        logger.warning(f"⚠️  Instant first match failed for {user_id}: {e}")
        return

    try:
        from core.pipeline_runner import generate_resumes_for_user

        resume_stats = await generate_resumes_for_user(user_id)
        logger.info(f"⚡ Instant resume generation for {user_id}: {resume_stats}")
    except Exception as e:
        logger.warning(f"⚠️  Instant resume generation failed for {user_id}: {e}")


@router.post("/confirm")
async def confirm_profile(payload: ConfirmProfileRequest, background_tasks: BackgroundTasks):
    supabase = get_supabase()
    profile_dict = payload.model_dump()
    resume_text = build_resume_text_from_profile(profile_dict)

    row = {
        "email": payload.basic_info.email,
        "name": payload.basic_info.full_name or None,
        "phone": payload.basic_info.phone or None,
        "location": payload.basic_info.location or None,
        "job_category": payload.job_category or None,
        "experience_level": payload.experience_level,
        "target_roles": payload.target_roles,
        "tools": payload.tools,
        "skills": payload.skills,
        "work_type": payload.work_type,
        "preferred_locations": payload.preferred_locations,
        "summary": payload.summary or None,
        "work_experience": [e.model_dump() for e in payload.work_experience],
        "projects": [p.model_dump() for p in payload.projects],
        "education": [e.model_dump() for e in payload.education],
        # Links are stored as the individual linkedin_url/portfolio_url/github_url
        # columns below — there is no combined "links" column in the users table.
        "confidence_flags": payload.confidence_flags,
        "resume_text": resume_text,
        "resume_file_path": payload.resume_file_path,
        # Unknown/blank template names silently fall back to the default —
        # a bad value here must never block someone from saving a profile.
        "resume_template": payload.resume_template if payload.resume_template in RESUME_TEMPLATES else "modern",
        "linkedin_url": payload.links.linkedin or None,
        "portfolio_url": payload.links.portfolio or None,
        "github_url": payload.links.github or None,
        "is_active": True,
    }

    # Newer columns — if this database hasn't run the migration yet, drop the
    # offending column and retry so a signup never fails on a missing column.
    newer_columns = ["resume_template", "projects"]
    while True:
        try:
            resp = supabase.table("users").upsert(row, on_conflict="email").execute()
            break
        except Exception as e:
            missing = next((c for c in newer_columns if c in row and c in str(e)), None)
            if missing is None:
                raise
            logger.warning(f"users.{missing} column missing — run the migration in database/schema.sql")
            row.pop(missing, None)
    if not resp.data:
        raise HTTPException(500, "Failed to save profile.")

    user_id = resp.data[0]["id"]
    background_tasks.add_task(_match_new_user, user_id)
    # The signed token is the user's key to their own dashboard — dashboard
    # endpoints no longer accept a bare user_id (core/access_token.py).
    from core.access_token import generate_dashboard_token
    return {"id": user_id, "dashboard_token": generate_dashboard_token(user_id)}
