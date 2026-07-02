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


@router.get("/{user_id}/dashboard")
async def get_dashboard(user_id: str):
    """Return a user's profile summary + their matched jobs for the dashboard."""
    supabase = get_supabase()

    user_resp = (
        supabase.table("users")
        .select("id, name, email, target_roles")
        .eq("id", user_id)
        .execute()
    )
    if not user_resp.data:
        raise HTTPException(404, "We couldn't find a profile for this link.")

    jobs_resp = (
        supabase.table("user_jobs")
        .select("id, match_score, pdf_url, digest_date, status, jobs(id, title, company, location, is_remote, source_url)")
        .eq("user_id", user_id)
        .order("match_score", desc=True)
        .execute()
    )

    return {"user": user_resp.data[0], "jobs": jobs_resp.data or []}
