"""
Unsubscribe — public, no auth, no CORS needed
───────────────────────────────────────────────
Clicked directly from an email link (full-page navigation, not an XHR from
the frontend), so this returns a small branded HTML page itself rather than
redirecting through the frontend — one less thing that can break a link
sitting in someone's inbox for weeks.
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from core.simple_html import render_message_page
from core.unsubscribe import verify_unsubscribe_token
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: str = Query(...)):
    user_id = verify_unsubscribe_token(token)
    if not user_id:
        return HTMLResponse(
            render_message_page(
                "Invalid link",
                "That link isn't valid",
                "This unsubscribe link is broken or has been tampered with. "
                "Email gargeypatel123@gmail.com and we'll unsubscribe you by hand.",
            ),
            status_code=400,
        )

    supabase = get_supabase()
    try:
        supabase.table("users").update({"is_subscribed": False}).eq("id", user_id).execute()
    except Exception as e:
        logger.error(f"   ❌ Unsubscribe failed for {user_id}: {e}")
        return HTMLResponse(
            render_message_page(
                "Something went wrong",
                "Couldn't process that",
                "Something went wrong on our end. Email gargeypatel123@gmail.com and we'll take care of it.",
            ),
            status_code=500,
        )

    logger.info(f"   Unsubscribed user {user_id} from digest emails.")
    return HTMLResponse(
        render_message_page(
            "Unsubscribed",
            "You're unsubscribed",
            "You won't get any more morning digest emails. Your dashboard and matches "
            "are still there whenever you want to check them yourself.",
        )
    )
