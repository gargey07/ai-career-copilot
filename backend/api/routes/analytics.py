"""
Analytics — signup funnel logging
──────────────────────────────────
Public, unauthenticated, fire-and-forget. The beta success metrics
(docs/PRODUCT_STRATEGY_BETA.md) need to know where signups drop off, not
just who finished — the admin overview previously only showed completed
users, with no visibility into how many people started and gave up.

Never lets analytics block or fail the actual signup flow: unknown event
names are silently ignored rather than erroring (so a stale frontend
build can't spam junk rows), and a DB failure here is logged, not raised.
"""
from __future__ import annotations
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()

# Fixed allowlist — matches the 3-stage funnel wired into the signup flow.
ALLOWED_EVENTS = {"signup_started", "profile_review_reached", "signup_completed"}


class TrackEventRequest(BaseModel):
    event: str
    session_id: str = ""
    user_id: str | None = None
    meta: dict = Field(default_factory=dict)


@router.post("/track")
async def track_event(payload: TrackEventRequest):
    if payload.event not in ALLOWED_EVENTS:
        return {"status": "ignored"}

    supabase = get_supabase()
    try:
        supabase.table("funnel_events").insert({
            "event": payload.event,
            "session_id": (payload.session_id or "")[:100] or None,
            "user_id": payload.user_id,
            "meta": payload.meta or {},
        }).execute()
    except Exception as e:
        logger.warning(f"   Funnel event logging failed ({payload.event}): {e}")

    return {"status": "ok"}
