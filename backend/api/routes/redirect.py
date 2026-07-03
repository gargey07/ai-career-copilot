"""
Apply-link redirect — public, no auth
───────────────────────────────────────
Every "Apply Now" link (dashboard + email) routes through here instead of
pointing straight at the job board, so we can measure the "Apply link
click rate" success metric from docs/PRODUCT_STRATEGY_BETA.md (previously
unmeasurable). Logs a click, best-effort, then 302s straight to the real
posting — tracking must never slow down or block someone applying.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from core.simple_html import render_message_page
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/r/{match_id}")
async def track_and_redirect(match_id: str):
    supabase = get_supabase()

    try:
        resp = supabase.table("user_jobs").select("id, click_count, jobs(source_url)").eq("id", match_id).execute()
    except Exception as e:
        logger.error(f"   ❌ Redirect lookup failed for {match_id}: {e}")
        return HTMLResponse(
            render_message_page(
                "Something went wrong",
                "Couldn't open that link",
                "Something went wrong on our end. Try again from your dashboard.",
            ),
            status_code=500,
        )

    if not resp.data:
        return HTMLResponse(
            render_message_page(
                "Link not found",
                "That link doesn't exist",
                "This apply link is invalid or has expired. Check your dashboard for the latest matches.",
            ),
            status_code=404,
        )

    row = resp.data[0]
    target = (row.get("jobs") or {}).get("source_url")
    if not target:
        return HTMLResponse(
            render_message_page(
                "Posting unavailable",
                "That job posting isn't available",
                "We don't have a direct link for this one. Check your dashboard for other matches.",
            ),
            status_code=404,
        )

    # Best-effort click tracking — a logging failure must never block someone
    # from actually applying.
    try:
        supabase.table("user_jobs").update({
            "click_count": (row.get("click_count") or 0) + 1,
            "last_clicked_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", match_id).execute()
    except Exception as e:
        logger.warning(f"   Click tracking failed for {match_id} (redirecting anyway): {e}")

    return RedirectResponse(url=target, status_code=302)
