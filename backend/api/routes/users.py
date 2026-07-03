"""
Users API — profile + dashboard reads
──────────────────────────────────────
The frontend can't read users/user_jobs directly: those tables have RLS
(auth.uid() = id) and the app has no Supabase auth session, so anon reads
are always blocked. These reads go through the backend's service_role
client (which bypasses RLS) instead — same pattern as /resumes/confirm.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()

# TICKET-008: resume feedback. 'up' needs no reason; 'down' gets an
# optional reason chip — never a required field, never blocks the click.
ALLOWED_FEEDBACK = {"up", "down"}
ALLOWED_REASONS = {
    "", "too_generic", "missing_skills", "wrong_project_highlighted",
    "experience_not_prioritized", "formatting_issue", "other",
}


class FeedbackRequest(BaseModel):
    feedback: str
    reason: str = ""


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
async def get_dashboard(user_id: str):
    """Return a user's profile summary + their matched jobs for the dashboard."""
    supabase = get_supabase()

    base_fields = (
        "id, name, email, target_roles, summary, work_experience, education, "
        "skills, tools, preferred_locations, phone, location, resume_file_path, "
        "linkedin_url, portfolio_url, github_url"
    )
    try:
        user_resp = (
            supabase.table("users").select(f"{base_fields}, projects").eq("id", user_id).execute()
        )
    except Exception:
        # projects is a newer column — dashboards must keep working on a
        # database that hasn't run the migration in database/schema.sql yet.
        user_resp = supabase.table("users").select(base_fields).eq("id", user_id).execute()
    if not user_resp.data:
        raise HTTPException(404, "We couldn't find a profile for this link.")

    full_user = user_resp.data[0]

    # feedback/feedback_reason are newer columns — same missing-migration
    # fallback pattern as the `projects` select above. optimized_resume_text
    # is fetched only to derive has_optimized_resume below — the raw text
    # itself is never shipped to the dashboard (see the transform below).
    jobs_fields = (
        "id, match_score, pdf_url, digest_date, status, optimized_resume_text, "
        "jobs(id, title, company, location, is_remote, source_url)"
    )
    try:
        jobs_resp = (
            supabase.table("user_jobs")
            .select(f"{jobs_fields}, feedback, feedback_reason")
            .eq("user_id", user_id)
            .order("match_score", desc=True)
            .execute()
        )
    except Exception:
        jobs_resp = (
            supabase.table("user_jobs")
            .select(jobs_fields)
            .eq("user_id", user_id)
            .order("match_score", desc=True)
            .execute()
        )

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
    }
    return {"user": user, "jobs": jobs}


@router.post("/{user_id}/matches/{match_id}/feedback")
async def submit_match_feedback(user_id: str, match_id: str, payload: FeedbackRequest):
    """
    Thumbs up/down on a generated resume — the cheapest real learning
    signal in the beta (docs/BETA_PRODUCT_LOG.md experiment #2). Verifies
    the match actually belongs to this user before writing, so one
    dashboard link can't overwrite another user's feedback.
    """
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


@router.post("/{user_id}/matches/{match_id}/retry-pdf")
async def retry_pdf(user_id: str, match_id: str, background_tasks: BackgroundTasks):
    """
    TICKET-020: the "Retry" button shown when a resume's PDF failed to
    generate (never leave a permanent 'Resume generating…' with no way
    out). Verifies ownership first. Re-renders from the already-generated
    optimized_resume_text — doesn't re-call the AI optimizer, so this is
    cheap and fixes infra failures (Chromium crash/timeout/upload) without
    burning another Gemini call.
    """
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
