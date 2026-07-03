"""
Digest Routes — T-004 + T-005
────────────────────────────────────────────────────────────────
POST /digest/run      — Protected: only callable by cron job (secret header)
POST /digest/request  — User-triggered: respects 20hr cooldown

T-005: POST /digest/run is protected by CRON_SECRET header.
       Returns immediately if cooldown not satisfied for all users.

T-004: POST /digest/request checks cooldown before triggering for a user.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from core.config import get_settings
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/digest", tags=["Digest"])


# ── T-005: Cron secret verification ──────────────────────────────────────────
def _verify_cron_secret(x_cron_secret: str = Header(None, alias="X-Cron-Secret")) -> str:
    """
    Dependency: verifies the X-Cron-Secret header matches CRON_SECRET env var.
    Blocks any public calls to /digest/run.
    """
    expected = settings.cron_secret
    if not expected:
        raise HTTPException(status_code=503, detail="Cron not configured (CRON_SECRET missing)")
    if x_cron_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid cron secret")
    return x_cron_secret


# ── Background pipeline runner ────────────────────────────────────────────────
async def _run_pipeline_background(test_mode: bool = False):
    """Run the full pipeline as a background task."""
    try:
        from pipeline import run_pipeline
        await run_pipeline(test_mode=test_mode)
    except Exception as e:
        logger.error(f"❌ Background pipeline failed: {e}")


# ── T-005: Protected cron trigger ─────────────────────────────────────────────
@router.post("/run", dependencies=[Depends(_verify_cron_secret)])
async def trigger_digest_run(
    background_tasks: BackgroundTasks,
    test: bool = False,
):
    """
    T-005: Protected endpoint — only callable by Render Cron Job.

    Protected by X-Cron-Secret header (must match CRON_SECRET env var).
    Fires the full pipeline in the background and returns immediately.
    Each user's 20hr cooldown is enforced inside the pipeline.

    Render Cron Job setup:
      - Schedule: every 30 min (*/30 * * * *)
      - Command: curl -X POST https://your-app.onrender.com/digest/run
                      -H "X-Cron-Secret: $CRON_SECRET"
    """
    logger.info(f"🕐 Cron triggered /digest/run (test={test})")
    background_tasks.add_task(_run_pipeline_background, test_mode=test)
    return {
        "status": "accepted",
        "message": "Pipeline started in background",
        "test_mode": test,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }


# ── T-004: User-triggered digest request (respects cooldown) ─────────────────
@router.post("/request")
async def request_digest(user_id: str, background_tasks: BackgroundTasks):
    """
    T-004: User-triggered digest request.

    Checks 20hr cooldown before triggering. If cooldown active,
    returns a friendly message with next available time instead of
    silently failing or sending anyway.

    Used by the "Get My First Digest" button in the frontend.
    """
    supabase = get_supabase()

    # Fetch user
    try:
        resp = supabase.table("users").select(
            "id, name, email, is_active, last_digest_sent_at"
        ).eq("id", user_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")

    user = resp.data
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account is inactive or unsubscribed")

    # T-004: Cooldown check
    last_sent = user.get("last_digest_sent_at")
    if last_sent:
        try:
            if isinstance(last_sent, str):
                last_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
            else:
                last_dt = last_sent

            now = datetime.now(timezone.utc)
            hours_since = (now - last_dt).total_seconds() / 3600
            gap = settings.min_digest_gap_hours

            if hours_since < gap:
                from datetime import timedelta
                next_send_dt = last_dt + timedelta(hours=gap)
                next_send_str = next_send_dt.strftime("%I:%M %p UTC")
                return JSONResponse(
                    status_code=429,
                    content={
                        "status": "cooldown",
                        "message": (
                            f"You already got a digest today — "
                            f"next one arrives at {next_send_str} tomorrow."
                        ),
                        "hours_remaining": round(gap - hours_since, 1),
                        "next_available_at": next_send_dt.isoformat(),
                    }
                )
        except Exception as e:
            logger.warning(f"Could not parse last_digest_sent_at: {e}")

    # Safe to trigger — run optimizer + email for this user only
    async def _run_for_user():
        try:
            from core.optimizer import run_optimizer_for_user
            from core.pdf_generator import run_pdf_generator_for_user
            from core.email_sender import send_morning_digest
            await run_optimizer_for_user(user_id)
            await run_pdf_generator_for_user(user_id)
            await send_morning_digest(user_id)
            # Update last sent time
            supabase.table("users").update({
                "last_digest_sent_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", user_id).execute()
        except Exception as e:
            logger.error(f"❌ On-demand digest failed for {user_id}: {e}")

    background_tasks.add_task(_run_for_user)

    return {
        "status": "accepted",
        "message": "Your digest is being prepared! Check your email in a few minutes.",
        "user": user.get("name"),
    }


# ── Health / status check ─────────────────────────────────────────────────────
@router.get("/status/{user_id}")
async def get_digest_status(user_id: str):
    """Check a user's last digest time and cooldown status."""
    supabase = get_supabase()

    try:
        resp = supabase.table("users").select(
            "name, last_digest_sent_at, is_active, preferred_digest_time"
        ).eq("id", user_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")

    user = resp.data or {}
    last_sent = user.get("last_digest_sent_at")
    cooldown_active = False
    hours_remaining = 0.0

    if last_sent:
        try:
            last_dt = datetime.fromisoformat(str(last_sent).replace("Z", "+00:00"))
            hours_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
            gap = settings.min_digest_gap_hours
            cooldown_active = hours_since < gap
            hours_remaining = max(0.0, round(gap - hours_since, 1))
        except Exception:
            pass

    return {
        "user": user.get("name"),
        "is_active": user.get("is_active"),
        "last_digest_sent_at": last_sent,
        "preferred_digest_time": str(user.get("preferred_digest_time", "07:00")),
        "cooldown_active": cooldown_active,
        "hours_remaining": hours_remaining,
    }
