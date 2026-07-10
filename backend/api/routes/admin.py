"""
Admin API — founder-only visibility & controls
──────────────────────────────────────────────
- POST /run-pipeline           → kick the fetch+match pipeline on demand
- GET  /overview                → users' progress + today's API usage vs budget caps
- GET  /users/{id}/inspect      → one user's profile + every match, with the
                                    actual AI-optimized resume/cover-letter text —
                                    for judging match and resume QUALITY, not just counts

Everything is gated by a shared secret (ADMIN_TOKEN); disabled entirely
until that's set. No general auth exists yet, so keep the token private.
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

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


def _audit(action: str, target_user_id: str | None = None, detail: dict | None = None) -> None:
    """
    T-016: record every sensitive admin action (who saw what, what changed).
    There's a single shared ADMIN_TOKEN today, so no admin identity column —
    the table exists so the trail is being built from day one and gains an
    admin_id the day real admin accounts exist. Best-effort: an audit
    failure (e.g. table not migrated yet) must never block the action.
    """
    try:
        get_supabase().table("admin_audit_log").insert({
            "action": action,
            "target_user_id": target_user_id,
            "detail": detail or {},
        }).execute()
    except Exception as e:
        logger.warning(f"   Audit log write failed ({action}): {e}")


async def _run_and_log() -> None:
    try:
        stats = await run_fetch_and_match()
        logger.info(f"✅ Manual pipeline run complete: {stats}")
    except Exception as e:
        logger.error(f"❌ Manual pipeline run failed: {e}", exc_info=True)
        from core.pipeline_runner import send_admin_alert
        await send_admin_alert("Manual pipeline run failed", f"The admin-triggered pipeline run crashed:\n\n{e!r}")


@router.post("/run-pipeline")
async def run_pipeline_now(background_tasks: BackgroundTasks, token: str = Query(..., description="Admin token")):
    """Trigger a fetch+match run in the background. Returns immediately."""
    _require_admin(token)
    _audit("pipeline_triggered")
    background_tasks.add_task(_run_and_log)
    return {
        "status": "started",
        "message": "Pipeline is running in the background. Give it a minute, then refresh your dashboard.",
    }


# ── Jobs pool search (T-023) — QA tool: "does category X return good jobs?" ────
@router.get("/jobs")
async def search_jobs(token: str = Query(..., description="Admin token"), q: str = Query("", max_length=80)):
    """Search the shared jobs pool by title. Empty q = newest 50."""
    _require_admin(token)
    supabase = get_supabase()
    fields = "id, title, company, location, source, search_category, collected_at, source_url"
    try:
        query = supabase.table("jobs").select(fields)
        if q.strip():
            query = query.ilike("title", f"%{q.strip()}%")
        resp = query.order("collected_at", desc=True).limit(50).execute()
    except Exception:
        # search_category is a newer column — degrade rather than 500.
        query = supabase.table("jobs").select("id, title, company, location, source, collected_at, source_url")
        if q.strip():
            query = query.ilike("title", f"%{q.strip()}%")
        resp = query.order("collected_at", desc=True).limit(50).execute()
    return {"jobs": resp.data or [], "query": q}


# ── Per-user quota overrides (T-023) ────────────────────────────────────────────
class OverridesUpdate(BaseModel):
    # None = clear the override (fall back to the global setting).
    resume_quota_override: int | None = None
    job_count_override: int | None = None


@router.patch("/users/{user_id}/overrides")
async def update_overrides(user_id: str, payload: OverridesUpdate, token: str = Query(..., description="Admin token")):
    """
    Set/clear per-user limits above or below the defaults (AI_JOBS_PER_USER /
    MAX_JOBS_PER_USER). Values are clamped to sane bounds — an override is a
    dial for beta support, not a way to accidentally 100x the AI bill.
    """
    _require_admin(token)

    def clamp(v: int | None, hi: int) -> int | None:
        if v is None:
            return None
        return max(0, min(int(v), hi))

    update = {
        "resume_quota_override": clamp(payload.resume_quota_override, 20),
        "job_count_override": clamp(payload.job_count_override, 50),
    }
    supabase = get_supabase()
    old = {}
    try:
        old_resp = supabase.table("users").select("resume_quota_override, job_count_override").eq("id", user_id).single().execute()
        old = old_resp.data or {}
    except Exception:
        pass
    try:
        supabase.table("users").update(update).eq("id", user_id).execute()
    except Exception as e:
        logger.error(f"   Override update failed for {user_id}: {e}")
        raise HTTPException(500, "Couldn't save overrides — the override columns may not be migrated yet.")

    _audit("overrides_changed", user_id, {"old": old, "new": update})
    return {"status": "ok", **update}


# ── Overview ──────────────────────────────────────────────────────────────────
# Which api_usage services to surface, with their configured daily caps.
# resume_parse rows are per-IP (resume_parse_ip_<addr>) and get summed.
def _usage_services() -> list[dict]:
    return [
        {"service": "gemini_generate", "label": "Gemini — AI generation", "limit": settings.gemini_generate_daily_limit},
        {"service": "gemini_embed",    "label": "Gemini — embeddings",    "limit": settings.gemini_embed_daily_limit},
        # AI generate_text fallback waterfall — only shows real usage once
        # Gemini errors/rate-limits and the corresponding key is set on
        # Render; otherwise these just sit at 0, which is expected.
        {"service": "groq",            "label": "Groq (fallback)",        "limit": settings.groq_daily_limit},
        {"service": "openrouter",      "label": "OpenRouter (fallback)",  "limit": settings.openrouter_daily_limit},
        {"service": "github_models",   "label": "GitHub Models (fallback)", "limit": settings.github_models_daily_limit},
        {"service": "mistral",         "label": "Mistral (fallback)",     "limit": settings.mistral_daily_limit},
        {"service": "cohere",          "label": "Cohere (fallback)",      "limit": settings.cohere_daily_limit},
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

    # Users — newest first so recent signups are on top. Override columns
    # are newer — fall back to the base select pre-migration.
    base_user_fields = "id, name, email, created_at, job_category, experience_level, is_active, resume_file_path"
    try:
        users_resp = (
            supabase.table("users")
            .select(f"{base_user_fields}, resume_quota_override, job_count_override")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        users_resp = (
            supabase.table("users")
            .select(base_user_fields)
            .order("created_at", desc=True)
            .execute()
        )
    users = users_resp.data or []

    # All match rows — aggregated per user in Python (beta-scale data; a few
    # thousand rows at most, not worth a custom SQL function yet).
    # click_count is a newer column — fall back gracefully pre-migration.
    try:
        matches_resp = supabase.table("user_jobs").select("user_id, status, digest_date, pdf_url, click_count").execute()
    except Exception:
        matches_resp = supabase.table("user_jobs").select("user_id, status, digest_date, pdf_url").execute()
    matches = matches_resp.data or []
    total_clicks = sum(m.get("click_count") or 0 for m in matches)

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
    # Dashboards now require a signed token (core/access_token.py) — the
    # admin's "View dashboard" links must carry one. Safe to hand out here:
    # this whole endpoint is already behind ADMIN_TOKEN.
    from core.access_token import generate_dashboard_token
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
            "dashboard_token": generate_dashboard_token(u["id"]),
            "resume_quota_override": u.get("resume_quota_override"),
            "job_count_override": u.get("job_count_override"),
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

    # Signup funnel — how many people started vs. actually finished, not
    # just the finished count the `users` table alone can show
    # (docs/PRODUCT_STRATEGY_BETA.md success metrics). funnel_events is a
    # newer table — missing entirely pre-migration, degrade to zeros.
    funnel = {"signup_started": 0, "profile_review_reached": 0, "signup_completed": 0}
    try:
        funnel_resp = supabase.table("funnel_events").select("event").execute()
        for row in funnel_resp.data or []:
            if row.get("event") in funnel:
                funnel[row["event"]] += 1
    except Exception:
        pass

    # Recent email sends — did each user's digest actually go out?
    # (T-015). email_logs predates most features, but degrade anyway.
    email_by_user = {u["id"]: u.get("email") for u in users}
    email_history = []
    try:
        logs_resp = (
            supabase.table("email_logs")
            .select("user_id, email_address, type, status, subject, error_message, sent_at")
            .order("sent_at", desc=True)
            .limit(50)
            .execute()
        )
        email_history = [
            {
                "user_email": row.get("email_address") or email_by_user.get(row.get("user_id"), ""),
                "type": row.get("type"),
                "status": row.get("status"),
                "subject": row.get("subject"),
                "error_message": row.get("error_message"),
                "sent_at": row.get("sent_at"),
            }
            for row in (logs_resp.data or [])
        ]
    except Exception:
        pass

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "usage_date": today,
        "totals": {
            "users": len(users),
            "active_users": sum(1 for u in users if u.get("is_active")),
            "jobs_in_pool": jobs_in_pool,
            "matches_delivered": len(matches),
            "apply_clicks": total_clicks,
        },
        "funnel": funnel,
        "api_usage": api_usage,
        "users": user_rows,
        "email_history": email_history,
    }


# ── Inspect — the "is the output actually good?" view ──────────────────────────
@router.get("/users/{user_id}/inspect")
async def inspect_user(user_id: str, token: str = Query(..., description="Admin token")):
    """
    Everything needed to judge quality, not just counts: the user's real
    profile, every match with the job's real title/description, and the
    actual AI-optimized resume + cover letter text for matches that have
    them. Read-only. Built because the ticket backlog was all plumbing —
    nobody had looked at whether the matches or the AI resumes are good.
    """
    _require_admin(token)
    _audit("inspect_user", user_id)
    supabase = get_supabase()

    user_resp = (
        supabase.table("users")
        .select(
            "id, name, email, job_category, experience_level, target_roles, "
            "skills, tools, summary, resume_text, resume_template, created_at, "
            "resume_file_path"
        )
        .eq("id", user_id)
        .execute()
    )
    if not user_resp.data:
        raise HTTPException(404, "User not found.")
    user = user_resp.data[0]

    # T-016: short-lived signed URL for the ORIGINAL uploaded resume in the
    # private bucket — 5-minute expiry, never a permanent public link, and
    # every issuance is audited.
    resume_signed_url = None
    resume_file_path = user.pop("resume_file_path", None)
    if resume_file_path:
        try:
            signed = supabase.storage.from_("resume-uploads").create_signed_url(resume_file_path, 300)
            resume_signed_url = (signed or {}).get("signedURL") or (signed or {}).get("signedUrl")
            if resume_signed_url:
                _audit("resume_url_issued", user_id, {"path": resume_file_path})
        except Exception as e:
            logger.warning(f"   Couldn't sign resume URL for {user_id}: {e}")

    match_fields = (
        "id, match_score, status, digest_date, pdf_url, optimized_resume_text, "
        "cover_letter_text, jobs(title, company, location, description, source, source_url)"
    )
    try:
        matches_resp = (
            supabase.table("user_jobs")
            .select(f"{match_fields}, feedback, feedback_reason, click_count, pdf_error_message")
            .eq("user_id", user_id)
            .order("digest_date", desc=True)
            .order("match_score", desc=True)
            .limit(30)
            .execute()
        )
    except Exception:
        # feedback/click_count/pdf_error_message are newer columns — degrade gracefully pre-migration.
        matches_resp = (
            supabase.table("user_jobs")
            .select(match_fields)
            .eq("user_id", user_id)
            .order("digest_date", desc=True)
            .order("match_score", desc=True)
            .limit(30)
            .execute()
        )
    matches = matches_resp.data or []

    return {
        "user": user,
        "resume_signed_url": resume_signed_url,
        "matches": [
            {
                "id": m["id"],
                "match_score": m.get("match_score"),
                "status": m.get("status"),
                "digest_date": m.get("digest_date"),
                "pdf_url": m.get("pdf_url"),
                "job": m.get("jobs") or {},
                "optimized_resume_text": m.get("optimized_resume_text"),
                "cover_letter_text": m.get("cover_letter_text"),
                "feedback": m.get("feedback"),
                "feedback_reason": m.get("feedback_reason"),
                "click_count": m.get("click_count") or 0,
                "pdf_error_message": m.get("pdf_error_message"),
            }
            for m in matches
        ],
    }


# ── Delete user ──────────────────────────────────────────────────────────────
@router.delete("/users/{user_id}")
async def delete_user(user_id: str, token: str = Query(..., description="Admin token")):
    """
    Founder cleanup tool — mainly for removing test/dummy accounts created
    while trying the product out. Hard delete: user_jobs cascades via FK
    (ON DELETE CASCADE in database/schema.sql); email_logs/pipeline_status/
    funnel_events keep their rows for audit purposes with user_id set to
    NULL (ON DELETE SET NULL) rather than being wiped. Also best-effort
    removes their uploaded resume file and generated PDFs from storage —
    a cleanup failure there is logged but never blocks the actual delete.
    """
    _require_admin(token)
    supabase = get_supabase()

    user_resp = supabase.table("users").select("id, name, email, resume_file_path").eq("id", user_id).execute()
    if not user_resp.data:
        raise HTTPException(404, "User not found.")
    user = user_resp.data[0]

    # Best-effort storage cleanup — private upload + any generated PDFs.
    try:
        if user.get("resume_file_path"):
            supabase.storage.from_("resume-uploads").remove([user["resume_file_path"]])
    except Exception as e:
        logger.warning(f"   Couldn't remove resume upload for {user_id}: {e}")

    try:
        # PDFs are stored nested by date: {user_id}/{date}/{filename}.pdf
        # (see core/pdf_generator.py) — list one level, then the next, to
        # build real object paths rather than treating date folders as files.
        all_paths = []
        for date_folder in (supabase.storage.from_("resumes").list(user_id) or []):
            folder_name = date_folder.get("name")
            if not folder_name:
                continue
            for f in (supabase.storage.from_("resumes").list(f"{user_id}/{folder_name}") or []):
                if f.get("name"):
                    all_paths.append(f"{user_id}/{folder_name}/{f['name']}")
        if all_paths:
            supabase.storage.from_("resumes").remove(all_paths)
    except Exception as e:
        logger.warning(f"   Couldn't remove generated PDFs for {user_id}: {e}")

    supabase.table("users").delete().eq("id", user_id).execute()
    _audit("user_deleted", user_id, {"email": user.get("email")})
    logger.info(f"   🗑️  Deleted user {user_id} ({user.get('email')}) via admin panel")

    return {"status": "deleted", "email": user.get("email")}
