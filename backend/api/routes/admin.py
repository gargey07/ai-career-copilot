"""
Admin API — manual pipeline trigger
────────────────────────────────────
Lets you kick the fetch+match pipeline on demand (to test / seed the
dashboard) without waiting for a scheduled run. Gated by a shared secret
(ADMIN_TOKEN); disabled entirely until that's set. No general auth exists
yet, so keep the token private.
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from core.config import get_settings
from core.pipeline_runner import run_fetch_and_match

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


async def _run_and_log() -> None:
    try:
        stats = await run_fetch_and_match()
        logger.info(f"✅ Manual pipeline run complete: {stats}")
    except Exception as e:
        logger.error(f"❌ Manual pipeline run failed: {e}", exc_info=True)


@router.post("/run-pipeline")
async def run_pipeline_now(background_tasks: BackgroundTasks, token: str = Query(..., description="Admin token")):
    """Trigger a fetch+match run in the background. Returns immediately."""
    if not settings.admin_token:
        raise HTTPException(403, "Pipeline trigger is disabled. Set ADMIN_TOKEN on the server to enable it.")
    if token != settings.admin_token:
        raise HTTPException(403, "Invalid admin token.")

    background_tasks.add_task(_run_and_log)
    return {
        "status": "started",
        "message": "Pipeline is running in the background. Give it a minute, then refresh your dashboard.",
    }
