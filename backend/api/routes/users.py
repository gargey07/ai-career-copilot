"""
Users API — profile + dashboard reads
──────────────────────────────────────
The frontend can't read users/user_jobs directly: those tables have RLS
(auth.uid() = id) and the app has no Supabase auth session, so anon reads
are always blocked. These reads go through the backend's service_role
client (which bypasses RLS) instead — same pattern as /resumes/confirm.

Every user-scoped endpoint here requires a signed dashboard token
(core/access_token.py) in the `t` query param — a raw user_id in the URL
is no longer enough to read a dashboard or write feedback/preferences.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from core.access_token import generate_dashboard_token, verify_dashboard_token
from core.config import get_settings
from core.usage_guard import check_budget
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

# TICKET-008: resume feedback. 'up' needs no reason; 'down' gets an
# optional reason chip — never a required field, never blocks the click.
ALLOWED_FEEDBACK = {"up", "down"}
ALLOWED_REASONS = {
    "", "too_generic", "missing_skills", "wrong_project_highlighted",
    "experience_not_prioritized", "formatting_issue", "other",
}

# Job-relevance feedback — a different signal from the resume thumbs above:
# "this JOB isn't for me" (feeds matching penalties in core/matcher.py),
# not "this resume needs work".
ALLOWED_JOB_REASONS = {
    "", "wrong_role", "too_senior", "too_junior", "wrong_location", "company",
}


def _require_dashboard_token(user_id: str, t: str) -> None:
    """401 unless `t` is a valid dashboard token FOR this exact user."""
    token_user = verify_dashboard_token(t or "")
    if token_user is None or token_user != user_id:
        raise HTTPException(
            401,
            "This link is invalid or has expired — request a fresh dashboard link below.",
        )


class FeedbackRequest(BaseModel):
    feedback: str
    reason: str = ""


class JobFeedbackRequest(BaseModel):
    reason: str = ""


class AppliedRequest(BaseModel):
    applied: bool = True


class DashboardLinkRequest(BaseModel):
    email: str


class PreferencesUpdate(BaseModel):
    preferred_digest_time: str


def compute_profile_strength(user: dict) -> int:
    """
    Profile Strength percentage — mirrors frontend/lib/profileStrength.ts
    (keep the weights in sync). Progress metric, never a gate.
    """
    def has(value) -> bool:
        return bool(str(value or "").strip())

    checks = [
        (20, bool(user.get("resume_file_path"))),
        (10, has(user.get("summary"))),
        (10, bool(user.get("work_experience") or [])),
        (10, bool(user.get("projects") or [])),
        (5, bool(user.get("education") or [])),
        (10, len(user.get("skills") or []) >= 3),
        (10, bool(user.get("target_roles") or [])),
        (5, bool(user.get("tools") or [])),
        (5, bool(user.get("preferred_locations") or [])),
        (5, has(user.get("phone")) and has(user.get("location"))),
        (5, has(user.get("linkedin_url"))),
        (5, has(user.get("portfolio_url")) or has(user.get("github_url"))),
    ]
    return sum(weight for weight, done in checks if done)


@router.get("/{user_id}/dashboard")
async def get_dashboard(user_id: str, t: str = Query("", description="Signed dashboard token")):
    """Return a user's profile summary + their matched jobs for the dashboard."""
    _require_dashboard_token(user_id, t)
    supabase = get_supabase()

    base_fields = (
        "id, name, email, target_roles, summary, work_experience, education, "
        "skills, tools, preferred_locations, phone, location, resume_file_path, "
        "linkedin_url, portfolio_url, github_url"
    )
    # `projects` and `preferred_digest_time` are newer columns — dashboards
    # must keep working on a database that hasn't run the corresponding
    # migration yet. Try progressively smaller selects rather than 500ing
    # outright the moment either column is missing.
    user_resp = None
    for fields in (
        f"{base_fields}, projects, preferred_digest_time",
        f"{base_fields}, projects",
        base_fields,
    ):
        try:
            user_resp = supabase.table("users").select(fields).eq("id", user_id).execute()
            break
        except Exception:
            continue
    if user_resp is None:
        raise HTTPException(500, "We couldn't load this profile — please try again.")
    if not user_resp.data:
        raise HTTPException(404, "We couldn't find a profile for this link.")

    full_user = user_resp.data[0]

    # feedback/job_feedback are newer columns — same missing-migration
    # fallback pattern as the `projects` select above. optimized_resume_text
    # is fetched only to derive has_optimized_resume below — the raw text
    # itself is never shipped to the dashboard (see the transform below).
    jobs_fields = (
        "id, match_score, pdf_url, digest_date, status, applied_at, optimized_resume_text, cover_letter_text, "
        "jobs(id, title, company, location, is_remote, source, source_url, salary_min, salary_max, currency)"
    )
    jobs_resp = None
    for extra in (", feedback, feedback_reason, job_feedback, job_feedback_reason, application_status, match_breakdown, recruiter_eval",
                  ", feedback, feedback_reason, job_feedback, job_feedback_reason, application_status, match_breakdown",
                  ", feedback, feedback_reason, job_feedback, job_feedback_reason",
                  ", feedback, feedback_reason",
                  ""):
        try:
            jobs_resp = (
                supabase.table("user_jobs")
                .select(f"{jobs_fields}{extra}")
                .eq("user_id", user_id)
                .order("match_score", desc=True)
                .execute()
            )
            break
        except Exception:
            continue
    if jobs_resp is None:
        raise HTTPException(500, "We couldn't load your matches — please try again.")

    # has_optimized_resume tells the dashboard whether a resume was ever
    # queued for this match at all — without it, "no pdf_url yet" is
    # ambiguous between "not selected for AI tailoring" (normal — only the
    # top few matches get one) and "generation failed" (the bug this fixes).
    # Sending the boolean, not the resume text itself, keeps the payload
    # small and doesn't leak resume content into a page that shows job
    # postings to whoever holds the dashboard link.
    jobs = []
    for row in (jobs_resp.data or []):
        row = dict(row)
        row["has_optimized_resume"] = bool(row.pop("optimized_resume_text", None))
        # Same boolean-not-content rule as the resume text above.
        row["has_cover_letter"] = bool(row.pop("cover_letter_text", None))
        jobs.append(row)

    # Only ship the fields the dashboard needs — the rest stays server-side.
    user = {
        "id": full_user["id"],
        "name": full_user.get("name"),
        "email": full_user.get("email"),
        "target_roles": full_user.get("target_roles") or [],
        "profile_strength": compute_profile_strength(full_user),
        "preferred_digest_time": full_user.get("preferred_digest_time"),
    }
    return {"user": user, "jobs": jobs}


@router.get("/{user_id}/profile")
async def get_profile(user_id: str, t: str = Query("", description="Signed dashboard token")):
    """
    Full editable profile for the /profile edit screen — the Profile
    Strength "Improve" CTA used to dump users back into the signup flow
    with a blank form. Same token gate as the dashboard; saving goes back
    through the existing /resumes/confirm upsert.
    """
    _require_dashboard_token(user_id, t)
    supabase = get_supabase()

    base_fields = (
        "id, name, email, phone, location, summary, work_experience, education, "
        "target_roles, skills, tools, job_category, experience_level, "
        "preferred_locations, work_type, linkedin_url, portfolio_url, github_url, "
        "resume_file_path, confidence_flags"
    )
    user_resp = None
    for fields in (
        f"{base_fields}, projects, resume_template, secondary_categories",
        f"{base_fields}, projects, resume_template",
        f"{base_fields}, projects",
        base_fields,
    ):
        try:
            user_resp = supabase.table("users").select(fields).eq("id", user_id).execute()
            break
        except Exception:
            continue
    if user_resp is None:
        raise HTTPException(500, "We couldn't load this profile — please try again.")
    if not user_resp.data:
        raise HTTPException(404, "We couldn't find a profile for this link.")

    u = user_resp.data[0]
    # Shape mirrors frontend/lib/profile.ts Profile — the editor consumes it as-is.
    return {
        "basic_info": {
            "full_name": u.get("name") or "",
            "email": u.get("email") or "",
            "phone": u.get("phone") or "",
            "location": u.get("location") or "",
        },
        "summary": u.get("summary") or "",
        "work_experience": u.get("work_experience") or [],
        "projects": u.get("projects") or [],
        "education": u.get("education") or [],
        "target_roles": u.get("target_roles") or [],
        "skills": u.get("skills") or [],
        "tools": u.get("tools") or [],
        "links": {
            "linkedin": u.get("linkedin_url") or "",
            "portfolio": u.get("portfolio_url") or "",
            "github": u.get("github_url") or "",
        },
        "confidence_flags": u.get("confidence_flags") or {},
        "job_category": u.get("job_category") or "",
        "secondary_categories": u.get("secondary_categories") or [],
        "experience_level": u.get("experience_level") or "mid",
        "preferred_locations": u.get("preferred_locations") or [],
        "work_type": u.get("work_type") or [],
        "resume_template": u.get("resume_template") or "modern",
        "resume_file_path": u.get("resume_file_path"),
    }


@router.post("/request-dashboard-link")
async def request_dashboard_link(payload: DashboardLinkRequest, request: Request):
    """
    "Get my dashboard link" — for returning users whose link was lost or
    invalidated. Always answers with the same generic success whether or
    not the email exists (no account enumeration); if it does exist, the
    signed link is emailed. Rate-limited per client IP.
    """
    client_ip = (request.client.host if request.client else "unknown") or "unknown"
    if not check_budget(f"dash_link_ip_{client_ip}", 5):
        raise HTTPException(429, "Too many link requests today — please try again tomorrow.")

    email = (payload.email or "").strip().lower()
    generic = {"status": "ok", "message": "If that email has an account, your dashboard link is on its way."}
    if not email or "@" not in email:
        return generic

    supabase = get_supabase()
    try:
        resp = supabase.table("users").select("id, name").eq("email", email).limit(1).execute()
    except Exception as e:
        logger.warning(f"   Dashboard-link lookup failed ({e})")
        return generic
    if not resp.data:
        return generic

    user = resp.data[0]
    token = generate_dashboard_token(user["id"])
    frontend = (settings.frontend_url or "https://ai-career-copilot-taupe-five.vercel.app").rstrip("/")
    link = f"{frontend}/dashboard?t={token}"
    first_name = (user.get("name") or "there").split()[0]
    html = (
        f"<p>Hi {first_name},</p>"
        f"<p>Here's your personal dashboard link:</p>"
        f"<p><a href=\"{link}\">Open my dashboard</a></p>"
        f"<p style='color:#64748B;font-size:13px'>Keep this link private — anyone who has it can see your job matches.</p>"
    )
    try:
        from core.email_sender import _send_email
        await _send_email(email, "Your AI Career Copilot dashboard link", html, unsubscribe_url="")
    except Exception as e:
        logger.error(f"   Couldn't email dashboard link to {email}: {e}")
    return generic


@router.patch("/{user_id}/preferences")
async def update_preferences(user_id: str, payload: PreferencesUpdate, t: str = Query("")):
    """T-012: Update user's preferred digest time."""
    _require_dashboard_token(user_id, t)
    supabase = get_supabase()

    try:
        supabase.table("users").update({
            "preferred_digest_time": payload.preferred_digest_time
        }).eq("id", user_id).execute()
    except Exception as e:
        logger.error(f"Failed to update preferences for {user_id}: {e}")
        raise HTTPException(500, "Could not save preferences.")

    return {"status": "ok"}


@router.post("/{user_id}/matches/{match_id}/feedback")
async def submit_match_feedback(user_id: str, match_id: str, payload: FeedbackRequest, t: str = Query("")):
    """
    Thumbs up/down on a generated resume — the cheapest real learning
    signal in the beta (docs/BETA_PRODUCT_LOG.md experiment #2). Verifies
    the match actually belongs to this user before writing, so one
    dashboard link can't overwrite another user's feedback.
    """
    _require_dashboard_token(user_id, t)
    if payload.feedback not in ALLOWED_FEEDBACK:
        raise HTTPException(400, "Feedback must be 'up' or 'down'.")
    if payload.reason not in ALLOWED_REASONS:
        raise HTTPException(400, "Unrecognized reason.")

    supabase = get_supabase()
    owns = supabase.table("user_jobs").select("id").eq("id", match_id).eq("user_id", user_id).execute()
    if not owns.data:
        raise HTTPException(404, "Match not found.")

    try:
        supabase.table("user_jobs").update({
            "feedback": payload.feedback,
            "feedback_reason": payload.reason or None,
            "feedback_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", match_id).execute()
    except Exception as e:
        logger.warning(f"   Feedback write failed for match {match_id} ({e}) — feedback columns may be unmigrated.")
        raise HTTPException(500, "Couldn't save your feedback — try again in a moment.")

    return {"status": "ok"}


@router.post("/{user_id}/matches/{match_id}/job-feedback")
async def submit_job_feedback(user_id: str, match_id: str, payload: JobFeedbackRequest, t: str = Query("")):
    """
    "This job isn't relevant to me" — a JOB-fit signal (distinct from the
    resume thumbs above). core/matcher.py reads these rows to exclude the
    same company and demote similar titles in future matching.
    """
    _require_dashboard_token(user_id, t)
    if payload.reason not in ALLOWED_JOB_REASONS:
        raise HTTPException(400, "Unrecognized reason.")

    supabase = get_supabase()
    owns = supabase.table("user_jobs").select("id").eq("id", match_id).eq("user_id", user_id).execute()
    if not owns.data:
        raise HTTPException(404, "Match not found.")

    try:
        supabase.table("user_jobs").update({
            "job_feedback": "not_relevant",
            "job_feedback_reason": payload.reason or None,
        }).eq("id", match_id).execute()
    except Exception as e:
        logger.warning(f"   Job-feedback write failed for match {match_id} ({e}) — job_feedback columns may be unmigrated.")
        raise HTTPException(500, "Couldn't save that — try again in a moment.")

    return {"status": "ok"}


@router.post("/{user_id}/matches/{match_id}/applied")
async def mark_applied(user_id: str, match_id: str, payload: AppliedRequest, t: str = Query("")):
    """
    User-asserted "I applied to this job" — the honest version of the
    Applications metric (docs/PRODUCT_STRATEGY_BETA.md: never display
    numbers we can't back). Toggling off reverts to 'emailed' (a safe,
    already-progressed state) rather than trying to reconstruct history.
    """
    _require_dashboard_token(user_id, t)
    supabase = get_supabase()
    owns = supabase.table("user_jobs").select("id").eq("id", match_id).eq("user_id", user_id).execute()
    if not owns.data:
        raise HTTPException(404, "Match not found.")

    update = (
        {"status": "applied", "applied_at": datetime.now(timezone.utc).isoformat()}
        if payload.applied
        else {"status": "emailed", "applied_at": None}
    )
    try:
        supabase.table("user_jobs").update(update).eq("id", match_id).execute()
    except Exception as e:
        logger.error(f"   Applied write failed for match {match_id}: {e}")
        raise HTTPException(500, "Couldn't save that — try again in a moment.")

    return {"status": "ok", "applied": payload.applied}


# Application tracker — strictly user-asserted transitions. "" clears the
# status (back to just "applied_at" from the Applied button).
ALLOWED_APPLICATION_STATUSES = {"", "applied", "interviewing", "offer", "rejected"}


class ApplicationStatusRequest(BaseModel):
    status: str


class CoverLetterRequest(BaseModel):
    regenerate: bool = False


async def _generate_resume_task(user_id: str, match_id: str) -> None:
    """Background: tailored resume text, then its PDF. Each half best-effort."""
    try:
        from core.optimizer import run_optimizer_for_match
        ok = await run_optimizer_for_match(user_id, match_id)
        if not ok:
            logger.warning(f"   On-demand resume generation produced nothing for match {match_id}")
            return
    except Exception as e:
        logger.error(f"   On-demand resume generation failed for match {match_id}: {e}")
        return
    try:
        from core.pdf_generator import generate_pdf_for_match
        await generate_pdf_for_match(match_id)
    except Exception as e:
        logger.warning(f"   On-demand PDF render failed for match {match_id} (resume text saved): {e}")


@router.post("/{user_id}/matches/{match_id}/generate-resume")
async def generate_resume_on_demand(user_id: str, match_id: str, background_tasks: BackgroundTasks, t: str = Query("")):
    """
    Per-job "Generate Tailored Resume" — the pipeline only auto-generates
    for the top few matches; this lets the user pick which OTHER match
    deserves one. Capped per day at the user's pipeline quota plus a small
    on-demand bonus, counted from rows that actually have resume text today.
    """
    _require_dashboard_token(user_id, t)
    supabase = get_supabase()

    owns = (
        supabase.table("user_jobs")
        .select("id, optimized_resume_text, pdf_url")
        .eq("id", match_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not owns.data:
        raise HTTPException(404, "Match not found.")
    row = owns.data[0]
    if row.get("optimized_resume_text"):
        return {"status": "already_generated", "message": "This match already has a tailored resume."}

    # Daily cap: pipeline quota (or admin override) + on-demand bonus.
    try:
        user_resp = supabase.table("users").select("resume_quota_override").eq("id", user_id).single().execute()
        override = (user_resp.data or {}).get("resume_quota_override")
    except Exception:
        override = None
    quota = (override if override is not None else settings.ai_jobs_per_user) + settings.on_demand_resume_bonus_per_day

    from datetime import date as _date
    today = _date.today().isoformat()
    generated_today = (
        supabase.table("user_jobs")
        .select("id, optimized_resume_text")
        .eq("user_id", user_id)
        .eq("digest_date", today)
        .not_.is_("optimized_resume_text", "null")
        .execute()
    )
    if len(generated_today.data or []) >= quota:
        raise HTTPException(
            429,
            "You've used today's tailored-resume allowance — more unlock tomorrow morning.",
        )

    background_tasks.add_task(_generate_resume_task, user_id, match_id)
    return {"status": "started", "message": "Generating your tailored resume — this can take up to a minute."}


@router.post("/{user_id}/matches/{match_id}/generate-cover-letter")
async def generate_cover_letter_on_demand(user_id: str, match_id: str, payload: CoverLetterRequest, t: str = Query("")):
    """
    On-demand cover letter for a specific job — never automatic (a full
    extra AI call per match; docs/PRODUCT_STRATEGY_BETA.md keeps costs
    honest). Returns the existing letter unless regenerate=true; capped
    per user per day.
    """
    _require_dashboard_token(user_id, t)
    supabase = get_supabase()

    owns = (
        supabase.table("user_jobs")
        .select("id, job_id, cover_letter_text")
        .eq("id", match_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not owns.data:
        raise HTTPException(404, "Match not found.")
    row = owns.data[0]

    if row.get("cover_letter_text") and not payload.regenerate:
        return {"status": "ok", "cover_letter": row["cover_letter_text"], "cached": True}

    if not check_budget(f"cover_letter_{user_id}", settings.cover_letters_per_user_daily):
        raise HTTPException(429, "You've used today's cover-letter allowance — more unlock tomorrow.")

    user_resp = supabase.table("users").select("name, resume_text").eq("id", user_id).single().execute()
    user = user_resp.data or {}
    if not user.get("resume_text"):
        raise HTTPException(400, "Add your resume first — the cover letter is written from it.")

    job_resp = supabase.table("jobs").select("title, company, description").eq("id", row["job_id"]).single().execute()
    job = job_resp.data
    if not job:
        raise HTTPException(404, "The job posting for this match is no longer available.")

    from core.optimizer import generate_cover_letter
    try:
        letter = await generate_cover_letter(
            name=user.get("name", "Applicant"),
            resume_text=user["resume_text"],
            job_title=job["title"],
            company=job["company"],
            job_description=job.get("description", ""),
        )
    except Exception as e:
        logger.error(f"   Cover-letter generation failed for match {match_id}: {e}")
        raise HTTPException(503, "Couldn't generate the letter right now — try again in a minute.")

    try:
        supabase.table("user_jobs").update({"cover_letter_text": letter}).eq("id", match_id).execute()
    except Exception as e:
        logger.warning(f"   Couldn't store cover letter for match {match_id}: {e}")

    return {"status": "ok", "cover_letter": letter, "cached": False}


@router.patch("/{user_id}/matches/{match_id}/application-status")
async def update_application_status(user_id: str, match_id: str, payload: ApplicationStatusRequest, t: str = Query("")):
    """
    User-asserted application progress (applied → interviewing → offer /
    rejected). Same honesty rule as the Applied button: we only ever show
    what the user themselves told us, never inferred pipeline stages.
    """
    _require_dashboard_token(user_id, t)
    status = (payload.status or "").strip()
    if status not in ALLOWED_APPLICATION_STATUSES:
        raise HTTPException(400, "Unrecognized status.")

    supabase = get_supabase()
    owns = supabase.table("user_jobs").select("id").eq("id", match_id).eq("user_id", user_id).execute()
    if not owns.data:
        raise HTTPException(404, "Match not found.")

    update = {
        "application_status": status or None,
        "application_status_updated_at": datetime.now(timezone.utc).isoformat() if status else None,
    }
    try:
        supabase.table("user_jobs").update(update).eq("id", match_id).execute()
    except Exception as e:
        logger.warning(f"   Application-status write failed for match {match_id} ({e}) — columns may be unmigrated.")
        raise HTTPException(500, "Couldn't save that — try again in a moment.")

    return {"status": "ok", "application_status": status or None}


@router.post("/{user_id}/matches/{match_id}/retry-pdf")
async def retry_pdf(user_id: str, match_id: str, background_tasks: BackgroundTasks, t: str = Query("")):
    """
    TICKET-020: the "Retry" button shown when a resume's PDF failed to
    generate (never leave a permanent 'Resume generating…' with no way
    out). Verifies ownership first. Re-renders from the already-generated
    optimized_resume_text — doesn't re-call the AI optimizer, so this is
    cheap and fixes infra failures (Chromium crash/timeout/upload) without
    burning another Gemini call.
    """
    _require_dashboard_token(user_id, t)
    supabase = get_supabase()
    owns = (
        supabase.table("user_jobs")
        .select("id, optimized_resume_text")
        .eq("id", match_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not owns.data:
        raise HTTPException(404, "Match not found.")
    if not owns.data[0].get("optimized_resume_text"):
        raise HTTPException(400, "This match doesn't have a tailored resume to render yet.")

    from core.pdf_generator import generate_pdf_for_match
    background_tasks.add_task(generate_pdf_for_match, match_id)
    return {"status": "started", "message": "Retrying — this can take up to a minute."}


# ── AI Application Review — add your own job, review it, then decide ──────────
# The advisor-workflow feature: instead of only analyzing jobs the pipeline
# fetched, a user can bring a job THEY found (link / screenshot / pasted
# text), review what we extracted from it, and get the recruiter verdict +
# improvement suggestions BEFORE spending a resume generation on it.

_JOB_ANALYSIS_BUDGET_MSG = (
    "You've used today's job-analysis allowance — more unlock tomorrow."
)

# Magic-byte sniffing, same never-trust-the-extension rule as resume uploads
# (resumes.py _sniff_extension). WebP is RIFF????WEBP — bytes 0-3 and 8-11.
_IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # same 5MB cap as resume uploads


def _sniff_image_mime(content: bytes) -> str | None:
    for signature, mime in _IMAGE_SIGNATURES:
        if content.startswith(signature):
            return mime
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _run_recruiter_eval(supabase, user_id: str, job: dict, match_id: str) -> dict | None:
    """Shared by confirm + analyze: run the eval, persist it on the match
    row (best-effort, same contract as optimizer._store_recruiter_eval)."""
    user_resp = (
        supabase.table("users")
        .select("resume_text, target_roles, experience_level")
        .eq("id", user_id)
        .single()
        .execute()
    )
    from core.recruiter import evaluate_match
    eval_result = await evaluate_match(user_resp.data or {}, job)
    if eval_result is not None:
        try:
            supabase.table("user_jobs").update({"recruiter_eval": eval_result}).eq("id", match_id).execute()
        except Exception as e:
            logger.info(f"   Couldn't store recruiter_eval ({e}) — run the recruiter_eval column migration.")
    return eval_result


@router.post("/{user_id}/job-intake/extract")
async def job_intake_extract(
    user_id: str,
    t: str = Query(""),
    url: str = Form(""),
    text: str = Form(""),
    image: UploadFile | None = File(None),
):
    """
    Step 1 of add-a-job: raw material (link / pasted text / screenshot) →
    structured draft for the user to REVIEW. Writes nothing to the
    database — the user hasn't confirmed anything yet.
    """
    _require_dashboard_token(user_id, t)

    if not check_budget(f"job_analysis_{user_id}", settings.job_analyses_per_user_daily):
        raise HTTPException(429, _JOB_ANALYSIS_BUDGET_MSG)

    url = (url or "").strip()
    raw_text = (text or "").strip()

    from core.job_intake import extract_job_draft, extract_text_from_image

    # Source priority: pasted text is what the user deliberately gave us;
    # a URL fetch is free; the vision call is the most expensive and least
    # reliable, so it's last.
    if not raw_text and url:
        from jobs.fetchers import fetch_job_page_text
        raw_text = await fetch_job_page_text(url)

    if not raw_text and image is not None:
        content = await image.read()
        if len(content) > _MAX_IMAGE_BYTES:
            raise HTTPException(400, "That screenshot is over 5MB — crop it to just the job posting.")
        mime = _sniff_image_mime(content)
        if mime is None:
            raise HTTPException(400, "That file doesn't look like a PNG, JPEG, or WebP image.")
        raw_text = await extract_text_from_image(content, mime) or ""
        if not raw_text:
            raise HTTPException(
                422, "We couldn't read the screenshot — paste the job description text instead."
            )

    if not raw_text:
        raise HTTPException(
            400,
            "We couldn't read anything from that — paste the job description text instead.",
        )

    draft = await extract_job_draft(raw_text)
    if draft is None:
        raise HTTPException(
            503, "The AI reader is busy right now — try again in a minute, or paste the details manually."
        )

    # Which fields need the user's attention on the review screen.
    missing = [k for k in ("title", "company", "location") if not draft.get(k)]
    return {"status": "ok", "draft": draft, "missing": missing, "url": url or None}


class JobConfirmRequest(BaseModel):
    title: str
    description: str
    company: str | None = None
    location: str | None = None
    url: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    employment_type: str | None = None
    is_remote: bool = False


@router.post("/{user_id}/job-intake/confirm")
async def job_intake_confirm(user_id: str, payload: JobConfirmRequest, t: str = Query("")):
    """
    Step 2 of add-a-job: the user has reviewed/corrected the extracted
    details. Store the job + match, run the recruiter analysis, and hand
    back the verdict — the Generate Resume / Cover Letter CTAs then use
    the returned match_id against the existing endpoints.
    """
    _require_dashboard_token(user_id, t)

    title = (payload.title or "").strip()
    description = (payload.description or "").strip()
    if not title or not description:
        raise HTTPException(400, "The job needs at least a title and its description text.")

    if not check_budget(f"job_analysis_{user_id}", settings.job_analyses_per_user_daily):
        raise HTTPException(429, _JOB_ANALYSIS_BUDGET_MSG)

    supabase = get_supabase()
    url = (payload.url or "").strip()

    # Reuse the fetched-jobs row when this URL is already in the job store
    # (source_url is the global dedup key) — the analysis then attaches to
    # the same job every other user's matches reference.
    job_row = None
    if url:
        existing = supabase.table("jobs").select("*").eq("source_url", url).execute()
        if existing.data:
            job_row = existing.data[0]

    if job_row is None:
        from uuid import uuid4
        from jobs.fetchers import normalize_job
        new_id = str(uuid4())
        job = normalize_job(
            source="user_submitted",
            external_id=new_id,
            title=title,
            company=(payload.company or "").strip(),
            location=(payload.location or "").strip(),
            description=description,
            # source_url is UNIQUE NOT NULL — text/screenshot submissions
            # get a synthetic one so two users pasting the same text don't
            # collide on an empty string.
            source_url=url or f"user-submitted:{new_id}",
            salary_min=payload.salary_min,
            salary_max=payload.salary_max,
            employment_type=(payload.employment_type or "").strip() or None,
            is_remote=payload.is_remote,
        )
        try:
            inserted = supabase.table("jobs").insert(job).execute()
            job_row = (inserted.data or [None])[0]
        except Exception:
            # Lost a race on source_url (two tabs, or another user adding
            # the same posting) — the row exists now, use it.
            if url:
                existing = supabase.table("jobs").select("*").eq("source_url", url).execute()
                job_row = (existing.data or [None])[0]
        if job_row is None:
            raise HTTPException(500, "Couldn't save that job — try again in a moment.")

    # One match row per user+job+day (same key the pipeline upserts on).
    from datetime import date as _date
    today = _date.today().isoformat()
    existing_match = (
        supabase.table("user_jobs")
        .select("id")
        .eq("user_id", user_id)
        .eq("job_id", job_row["id"])
        .eq("digest_date", today)
        .execute()
    )
    if existing_match.data:
        match_id = existing_match.data[0]["id"]
    else:
        created = (
            supabase.table("user_jobs")
            .insert({
                "user_id": user_id,
                "job_id": job_row["id"],
                "digest_date": today,
                "status": "matched",
                # match_score deliberately left NULL: no pipeline scoring ran
                # for this pair, and the recruiter verdict below is the honest
                # surface — never a made-up percentage.
            })
            .execute()
        )
        if not created.data:
            raise HTTPException(500, "Couldn't save that job — try again in a moment.")
        match_id = created.data[0]["id"]

    eval_result = await _run_recruiter_eval(supabase, user_id, job_row, match_id)
    return {
        "status": "ok",
        "match_id": match_id,
        "job": {
            "id": job_row["id"],
            "title": job_row.get("title"),
            "company": job_row.get("company"),
            "location": job_row.get("location"),
            "source": job_row.get("source"),
        },
        "recruiter_eval": eval_result,
        "eval_pending": eval_result is None,
    }


class AnalyzeRequest(BaseModel):
    regenerate: bool = False


@router.post("/{user_id}/matches/{match_id}/analyze")
async def analyze_match(user_id: str, match_id: str, payload: AnalyzeRequest, t: str = Query("")):
    """
    On-demand recruiter analysis for a pipeline-found match. The pipeline
    only evaluates the top few matches it generates resumes for — this
    lets the user ask "should I apply?" about any other job on their
    dashboard BEFORE spending a resume generation on it.
    """
    _require_dashboard_token(user_id, t)
    supabase = get_supabase()

    owns = (
        supabase.table("user_jobs")
        .select("id, job_id, recruiter_eval")
        .eq("id", match_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not owns.data:
        raise HTTPException(404, "Match not found.")
    row = owns.data[0]

    if row.get("recruiter_eval") and not payload.regenerate:
        return {"status": "ok", "recruiter_eval": row["recruiter_eval"], "cached": True}

    if not check_budget(f"job_analysis_{user_id}", settings.job_analyses_per_user_daily):
        raise HTTPException(429, _JOB_ANALYSIS_BUDGET_MSG)

    job_resp = supabase.table("jobs").select("title, company, description").eq("id", row["job_id"]).single().execute()
    if not job_resp.data:
        raise HTTPException(404, "The job posting for this match is no longer available.")

    eval_result = await _run_recruiter_eval(supabase, user_id, job_resp.data, match_id)
    if eval_result is None:
        raise HTTPException(503, "The AI recruiter is busy right now — try again in a minute.")
    return {"status": "ok", "recruiter_eval": eval_result, "cached": False}
