"""
AI Career Copilot — FastAPI Application Entry Point
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import get_settings
from api.routes import resumes, suggestions, users, admin, unsubscribe, redirect, analytics

# ── Logger Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

settings = get_settings()


# ── Startup self-heal: Playwright Chromium ───────────────────────────────────
async def _ensure_chromium_installed() -> None:
    """
    Render's build step installs Chromium for PDF rendering, but that install
    has failed silently in production before (build shows green, then every
    PDF errors with "Executable doesn't exist" until someone notices). This
    runs `playwright install chromium` again at startup as a safety net —
    it's idempotent (fast no-op when the browser is already there, downloads
    it when it isn't), so a bad build self-heals on boot instead of leaving
    PDFs broken until the next manual clear-cache redeploy.

    Runs as a background task so it never delays /health — Render kills
    deploys whose health check doesn't respond quickly.
    """
    if os.environ.get("CHROMIUM_EXECUTABLE_PATH"):
        return  # host provides its own browser; nothing to install
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        if proc.returncode == 0:
            logger.info("✅ Playwright Chromium verified/installed (startup check)")
        else:
            tail = (out or b"")[-500:].decode(errors="replace")
            logger.error(f"❌ Startup Chromium install failed (rc={proc.returncode}): {tail}")
    except Exception as e:
        logger.error(f"❌ Startup Chromium install crashed: {e}")


# ── Daily pipeline scheduler ─────────────────────────────────────────────────
# Users are in India; DIGEST_TIME ("07:00") is interpreted as IST.
IST = timezone(timedelta(hours=5, minutes=30))
_SCHEDULER_POLL_SECONDS = 300


def _user_slot(user: dict) -> str:
    """preferred_digest_time ('07:00:00' TIME, may be null/missing) -> 'HH:MM'."""
    raw = str(user.get("preferred_digest_time") or settings.digest_time)
    return raw[:5]


async def _scheduler_tick() -> None:
    """
    One pass of the daily scheduler. Users pick their own digest slot
    (preferred_digest_time, default 07:00 IST), so delivery is per-user:

    1. When the first due user of the day appears, run the fetch/embed/match
       half once (day-locked via check_budget("daily_pipeline", 1)) — this
       guarantees fresh matches exist before the earliest delivery.
    2. Deliver (resumes → PDFs → digest email) to each user whose slot has
       arrived, each behind their own once-per-day usage-guard lock, so
       restarts can't double-deliver and later ticks skip already-served
       users without touching the optimizer at all. A user whose slot was
       missed while the instance slept gets caught up on the next tick —
       the condition is "slot <= now", not an exact-minute match.

    Manual admin "Run pipeline now" stays independent and immediate
    (idempotent stages + email_logs make overlap safe).
    """
    from core.usage_guard import check_budget
    from core.pipeline_runner import (
        run_fetch_and_match_jobs_only,
        _run_delivery_for_user,
        send_admin_alert,
    )
    from database.supabase_client import get_supabase

    supabase = get_supabase()
    now_hhmm = datetime.now(IST).strftime("%H:%M")

    # preferred_digest_time is a newer column — fall back to the global
    # default for everyone if the migration hasn't run.
    try:
        users = (
            supabase.table("users")
            .select("id, preferred_digest_time")
            .eq("is_active", True)
            .execute()
        ).data or []
    except Exception:
        users = (
            supabase.table("users").select("id").eq("is_active", True).execute()
        ).data or []

    due = [u for u in users if _user_slot(u) <= now_hhmm]
    if not due:
        return

    if check_budget("daily_pipeline", 1):
        logger.info("⏰ Scheduler: first due slot reached — running fetch/match for all users")
        try:
            stats = await run_fetch_and_match_jobs_only()
            logger.info(f"⏰ Scheduler: fetch/match done — {stats}")
        except Exception as e:
            logger.error(f"❌ Scheduler fetch/match failed: {e}", exc_info=True)
            await send_admin_alert(
                "Daily fetch/match failed",
                f"The scheduled fetch/embed/match run crashed at {now_hhmm} IST:\n\n{e!r}",
            )
            # Deliveries still proceed — yesterday's unprocessed matches may
            # exist, and each stage degrades gracefully on its own.

    for user in due:
        if not check_budget(f"daily_delivery_{user['id']}", 1):
            continue  # already delivered today
        logger.info(f"⏰ Scheduler: delivering to user {user['id']} (slot {_user_slot(user)})")
        try:
            await _run_delivery_for_user(user["id"])
        except Exception as e:
            logger.error(f"❌ Scheduled delivery failed for {user['id']}: {e}", exc_info=True)
            await send_admin_alert(
                "Digest delivery failed",
                f"Delivery for user {user['id']} (slot {_user_slot(user)}) crashed:\n\n{e!r}",
            )

    # Same-day retry: the per-user delivery day-lock above only runs once,
    # so a digest email that failed (e.g. a transient provider outage) would
    # otherwise stay dead until tomorrow even though the resume/PDF already
    # exist. Re-attempt just the email step for anyone whose latest attempt
    # today failed, capped at 3 tries/user/day so a persistent outage can't
    # retry forever. send_morning_digest handles its own failure logging and
    # admin alert internally.
    from datetime import date as _date
    try:
        logs_resp = (
            supabase.table("email_logs")
            .select("user_id, status, sent_at")
            .eq("type", "morning_digest")
            .gte("sent_at", _date.today().isoformat())
            .order("sent_at", desc=True)
            .execute()
        )
        latest_status: dict[str, str] = {}
        for row in logs_resp.data or []:
            uid = row.get("user_id")
            if uid and uid not in latest_status:
                latest_status[uid] = row.get("status")
        retry_candidates = [uid for uid, status in latest_status.items() if status == "failed"]
    except Exception as e:
        logger.warning(f"   Couldn't check email_logs for digest retry candidates: {e}")
        retry_candidates = []

    if retry_candidates:
        from core.email_sender import send_morning_digest
        for uid in retry_candidates:
            if not check_budget(f"digest_retry_{uid}", 3):
                continue
            logger.info(f"⏰ Scheduler: retrying failed digest for user {uid}")
            try:
                await send_morning_digest(uid)
            except Exception as e:
                logger.error(f"❌ Digest retry crashed for {uid}: {e}", exc_info=True)


async def _daily_pipeline_scheduler() -> None:
    """
    In-process daily scheduler — no external cron needed. GitHub's scheduled
    workflows proved unreliable (measured firing every 1-3 hours on a */10
    schedule) and asking the founder to click "Run pipeline now" every
    morning doesn't scale past day one. See _scheduler_tick for semantics.
    """
    while True:
        try:
            await _scheduler_tick()
        except Exception as e:
            logger.error(f"❌ Daily pipeline scheduler error: {e}", exc_info=True)
        await asyncio.sleep(_SCHEDULER_POLL_SECONDS)


# ── App Lifespan ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    logger.info(f"🚀 AI Career Copilot API starting — env: {settings.app_env}")
    chromium_task = asyncio.create_task(_ensure_chromium_installed())
    # Auto-pipeline only in production — a local dev boot must not consume
    # the day's pipeline slot or hammer job APIs.
    scheduler_task = (
        asyncio.create_task(_daily_pipeline_scheduler()) if settings.is_production else None
    )
    yield
    chromium_task.cancel()
    if scheduler_task:
        scheduler_task.cancel()
    logger.info("👋 AI Career Copilot API shutting down")


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Career Copilot API",
    description="Backend API for AI-powered job discovery, matching, and resume generation.",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Vercel gives every deployment (production + every branch preview) its own
# unique *.vercel.app subdomain under the team's namespace. Requiring an
# exact FRONTEND_URL match means CORS breaks every time a different preview
# URL is used. Allow anything under this specific Vercel team's subdomain
# (not *.vercel.app broadly — that's a shared multi-tenant domain and would
# let any other developer's Vercel-hosted app make credentialed requests
# here too). FRONTEND_URL still works as an extra explicit origin, e.g. for
# a custom domain later, or if your production URL doesn't match this regex.
VERCEL_TEAM_ORIGIN_REGEX = r"^https://.*gargeypatel123-2282s-projects\.vercel\.app$"

# Confirmed production domain — doesn't match the regex above since Vercel's
# stable production URL for this project doesn't include the team slug.
# Hardcoded rather than relying solely on the FRONTEND_URL env var being
# entered correctly, so a typo in Render's dashboard can't break this again.
KNOWN_PRODUCTION_ORIGIN = "https://ai-career-copilot-taupe-five.vercel.app"

allowed_origins = (
    ["*"]
    if settings.is_development
    else list({KNOWN_PRODUCTION_ORIGIN, *[o for o in [settings.frontend_url] if o]})
)
allow_origin_regex = None if settings.is_development else VERCEL_TEAM_ORIGIN_REGEX


# ── Global Error Handler ─────────────────────────────────────────────────────
# A plain @app.exception_handler(Exception) gets special-cased by Starlette:
# it's pulled out into ServerErrorMiddleware, which sits OUTSIDE
# CORSMiddleware in the stack, so its responses never get CORS headers —
# the browser can't read them and shows a generic network failure with zero
# detail instead of the real error. Using an actual middleware instead, and
# registering it BEFORE CORSMiddleware below (Starlette builds the stack in
# reverse-add order, so this ends up INSIDE CORSMiddleware), keeps the error
# response flowing back through CORS header injection correctly.
class CatchExceptionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
            return JSONResponse(status_code=500, content={"detail": f"Internal server error: {exc}"})


app.add_middleware(CatchExceptionsMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "ok",
        "service": "AI Career Copilot API",
        "version": "2.0.0",
        "env": settings.app_env,
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


app.include_router(resumes.router,     prefix="/api/resumes",     tags=["Resumes"])
app.include_router(suggestions.router, prefix="/api/suggestions", tags=["Suggestions"])
app.include_router(users.router,       prefix="/api/users",       tags=["Users"])
app.include_router(admin.router,       prefix="/api/admin",       tags=["Admin"])
app.include_router(analytics.router,   prefix="/api/analytics",   tags=["Analytics"])
# No prefix: these are full-page links clicked from an email or dashboard,
# kept short and stable at the API root rather than nested under /api.
app.include_router(unsubscribe.router, tags=["Unsubscribe"])
app.include_router(redirect.router,    tags=["Redirect"])

# ── Future routers (uncomment as you build each phase) ───────────────────────
# from api.routes import auth, users, jobs, admin
# app.include_router(auth.router,    prefix="/api/auth",    tags=["Auth"])
# app.include_router(users.router,   prefix="/api/users",   tags=["Users"])
# app.include_router(jobs.router,    prefix="/api/jobs",    tags=["Jobs"])
# app.include_router(admin.router,   prefix="/api/admin",   tags=["Admin"])
