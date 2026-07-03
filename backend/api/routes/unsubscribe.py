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

from core.unsubscribe import verify_unsubscribe_token
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()

# Design-system tokens (docs/design-system.md), inlined — this page loads
# standalone with no build step.
_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; background: #F8FAFC; color: #0F2F3A;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 24px; }}
  .card {{ max-width: 420px; width: 100%; background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px;
           padding: 32px; text-align: center; }}
  h1 {{ font-size: 20px; margin: 0 0 12px; }}
  p {{ font-size: 14px; color: #64748B; line-height: 1.6; margin: 0; }}
  a {{ color: #B45309; }}
</style></head>
<body><div class="card"><h1>{heading}</h1><p>{body}</p></div></body></html>"""


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: str = Query(...)):
    user_id = verify_unsubscribe_token(token)
    if not user_id:
        return HTMLResponse(
            _PAGE.format(
                title="Invalid link",
                heading="That link isn't valid",
                body="This unsubscribe link is broken or has been tampered with. "
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
            _PAGE.format(
                title="Something went wrong",
                heading="Couldn't process that",
                body="Something went wrong on our end. Email gargeypatel123@gmail.com and we'll take care of it.",
            ),
            status_code=500,
        )

    logger.info(f"   Unsubscribed user {user_id} from digest emails.")
    return HTMLResponse(
        _PAGE.format(
            title="Unsubscribed",
            heading="You're unsubscribed",
            body="You won't get any more morning digest emails. Your dashboard and matches "
            "are still there whenever you want to check them yourself.",
        )
    )
