"""
Admin API — founder-only visibility & controls
──────────────────────────────────────────────
- POST /run-pipeline  → kick the fetch+match pipeline on demand
- GET  /overview      → users' progress + today's API usage vs budget caps

Everything is gated by a shared secret (ADMIN_TOKEN); disabled entirely
until that's set. No general auth exists yet, so keep the token private.
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from core.config import get_settings
from core.pipeline_runner import run_fetch_and_match
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


def _require_admin(token: str) -> None:
    if not settings.admin_token:
        raise HTTPException(403, "Admin access is disabled. Set ADMIN_TOKEN on the server to enable it.")
    if token != settings.admin_token:
        raise HTTPException(403, "Invalid admin token.")


async def _run_and_log() -> None:
    try:
        stats = await run_fetch_and_match()
        logger.info(f"✅ Manual pipeline run complete: {stats}")
    except Exception as e:
        logger.error(f"❌ Manual pipeline run failed: {e}", exc_info=True)


@router.post("/run-pipeline")
async def run_pipeline_now(background_tasks: BackgroundTasks, token: str = Query(..., description="Admin token")):
    """Trigger a fetch+match run in the background. Returns immediately."""
    _require_admin(token)
    background_tasks.add_task(_run_and_log)
    return {
        "status": "started",
        "message": "Pipeline is running in the background. Give it a minute, then refresh your dashboard.",
    }


# ── Overview ──────────────────────────────────────────────────────────────────
# Which api_usage services to surface, with their configured daily caps.
# resume_parse rows are per-IP (resume_parse_ip_<addr>) and get summed.
def _usage_services() -> list[dict]:
    return [
        {"service": "gemini_generate", "label": "Gemini — AI generation", "limit": settings.gemini_generate_daily_limit},
        {"service": "gemini_embed",    "label": "Gemini — embeddings",    "limit": settings.gemini_embed_daily_limit},
        {"service": "adzuna",          "label": "Adzuna job search",      "limit": settings.adzuna_daily_limit},
        {"service": "jsearch",         "label": "JSearch (RapidAPI)",     "limit": settings.jsearch_daily_limit},
        {"service": "openai",          "label": "OpenAI",                 "limit": settings.openai_daily_limit},
        {"service": "resend",          "label": "Resend email",           "limit": settings.resend_daily_limit},
        {"service": "gmail",           "label": "Gmail digests",          "limit": settings.gmail_daily_limit},
        {"service": "resume_parse",    "label": "Resume uploads (all users)", "limit": 0},  # per-IP cap, no global cap
    ]


@router.get("/overview")
async def admin_overview(token: str = Query(..., description="Admin token")):
    """
    Founder dashboard data: every user's progress through the funnel
    (profile → matches → resumes → applications) and today's API usage
    against the configured daily budget caps.
    """
    _require_admin(token)
    supabase = get_supabase()
    today = date.today().isoformat()

    # Users — newest first so recent signups are on top.
    users_resp = (
        supabase.table("users")
        .select("id, name, email, created_at, job_category, experience_level, is_active, resume_file_path")
        .order("created_at", desc=True)
        .execute()
    )
    users = users_resp.data or []

    # All match rows — aggregated per user in Python (beta-scale data; a few
    # thousand rows at most, not worth a custom SQL function yet).
    matches_resp = supabase.table("user_jobs").select("user_id, status, digest_date, pdf_url").execute()
    matches = matches_resp.data or []

    per_user: dict[str, dict] = {}
    for m in matches:
        stats = per_user.setdefault(m["user_id"], {
            "matches_total": 0, "matches_today": 0, "resumes_ready": 0,
            "applied": 0, "interviewing": 0, "offered": 0, "last_digest_date": None,
        })
        stats["matches_total"] += 1
        if m.get("digest_date") == today:
            stats["matches_today"] += 1
        if m.get("pdf_url"):
            stats["resumes_ready"] += 1
        status = m.get("status")
        if status in ("applied", "interviewing", "offered"):
            stats[status] += 1
        if m.get("digest_date") and (stats["last_digest_date"] is None or m["digest_date"] > stats["last_digest_date"]):
            stats["last_digest_date"] = m["digest_date"]

    empty_stats = {
        "matches_total": 0, "matches_today": 0, "resumes_ready": 0,
        "applied": 0, "interviewing": 0, "offered": 0, "last_digest_date": None,
    }
    user_rows = [
        {
            "id": u["id"],
            "name": u.get("name") or "—",
            "email": u.get("email") or "—",
            "joined_at": u.get("created_at"),
            "job_category": u.get("job_category") or "—",
            "experience_level": u.get("experience_level") or "—",
            "is_active": bool(u.get("is_active")),
            "has_resume": bool(u.get("resume_file_path")),
            **per_user.get(u["id"], empty_stats),
        }
        for u in users
    ]

    # Jobs pool size — how many jobs the fetchers have collected so far.
    jobs_resp = supabase.table("jobs").select("id", count="exact").limit(1).execute()
    jobs_in_pool = jobs_resp.count if jobs_resp.count is not None else 0

    # Today's API usage vs the configured caps (0 = uncapped).
    usage_resp = supabase.table("api_usage").select("service, count").eq("usage_date", today).execute()
    used: dict[str, int] = {}
    resume_parse_total = 0
    for row in usage_resp.data or []:
        if str(row["service"]).startswith("resume_parse_ip_"):
            resume_parse_total += row.get("count") or 0
        else:
            used[row["service"]] = row.get("count") or 0
    used["resume_parse"] = resume_parse_total

    api_usage = [
        {**svc, "used": used.get(svc["service"], 0)}
        for svc in _usage_services()
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "usage_date": today,
        "totals": {
            "users": len(users),
            "active_users": sum(1 for u in users if u.get("is_active")),
            "jobs_in_pool": jobs_in_pool,
            "matches_delivered": len(matches),
        },
        "api_usage": api_usage,
        "users": user_rows,
    }
