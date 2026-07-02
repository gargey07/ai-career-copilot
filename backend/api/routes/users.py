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

from fastapi import APIRouter, HTTPException

from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


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
        (15, bool(user.get("work_experience") or [])),
        (10, bool(user.get("education") or [])),
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

    user_resp = (
        supabase.table("users")
        .select(
            "id, name, email, target_roles, summary, work_experience, education, "
            "skills, tools, preferred_locations, phone, location, resume_file_path, "
            "linkedin_url, portfolio_url, github_url"
        )
        .eq("id", user_id)
        .execute()
    )
    if not user_resp.data:
        raise HTTPException(404, "We couldn't find a profile for this link.")

    full_user = user_resp.data[0]

    jobs_resp = (
        supabase.table("user_jobs")
        .select("id, match_score, pdf_url, digest_date, status, jobs(id, title, company, location, is_remote, source_url)")
        .eq("user_id", user_id)
        .order("match_score", desc=True)
        .execute()
    )

    # Only ship the fields the dashboard needs — the rest stays server-side.
    user = {
        "id": full_user["id"],
        "name": full_user.get("name"),
        "email": full_user.get("email"),
        "target_roles": full_user.get("target_roles") or [],
        "profile_strength": compute_profile_strength(full_user),
    }
    return {"user": user, "jobs": jobs_resp.data or []}
