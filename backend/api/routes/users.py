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

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
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
        "id, match_score, pdf_url, digest_date, status, applied_at, optimized_resume_text, "
        "jobs(id, title, company, location, is_remote, source_url)"
    )
    jobs_resp = None
    for extra in (", feedback, feedback_reason, job_feedback, job_feedback_reason",
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
