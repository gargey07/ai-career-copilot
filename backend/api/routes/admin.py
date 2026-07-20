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
import os
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


async def _backfill_experience() -> None:
    """One-time-ish: parse required experience out of the description for
    every stored job that predates the required_experience_months column
    (all NULL there). Without this, the experience gate treats old jobs as
    'unknown' — which passes — and a fresher keeps seeing '7+ years' roles
    that state the requirement only in their description text. Idempotent:
    already-filled rows are never touched, so re-running is harmless."""
    from jobs.fetchers import experience_months_from_text

    supabase = get_supabase()
    updated = scanned = 0
    page_size = 200
    offset = 0
    try:
        while True:
            resp = (
                supabase.table("jobs")
                .select("id, description")
                .is_("required_experience_months", "null")
                .order("collected_at", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = resp.data or []
            if not rows:
                break
            for row in rows:
                scanned += 1
                months = experience_months_from_text(row.get("description") or "")
                if months:
                    supabase.table("jobs").update(
                        {"required_experience_months": months}
                    ).eq("id", row["id"]).execute()
                    updated += 1
            if len(rows) < page_size:
                break
            offset += page_size
        logger.info(f"✅ Experience backfill: {updated}/{scanned} NULL-experience jobs got a parsed value")
    except Exception as e:
        logger.error(f"❌ Experience backfill failed after {updated}/{scanned}: {e}")


@router.post("/backfill-experience")
async def backfill_experience_now(background_tasks: BackgroundTasks, token: str = Query(..., description="Admin token")):
    """Parse experience requirements from existing jobs' descriptions in
    the background. Run once after the required_experience_months
    migration; safe to re-run. Also worth re-running any time
    experience_months_from_text's regex is improved (2026-07: widened to
    catch phrasings like "5+ years in a similar role" that don't contain
    the word "experience") — it only touches rows still NULL, so it picks
    up newly-parseable jobs without re-processing settled ones."""
    _require_admin(token)
    background_tasks.add_task(_audit, "experience_backfill_triggered")
    background_tasks.add_task(_backfill_experience)
    return {
        "status": "started",
        "message": "Backfilling experience data from job descriptions in the background — check the server log for the summary line.",
    }


async def _backfill_seniority() -> None:
    """One-time-ish, same pattern as _backfill_experience: infer
    seniority_level from the title for every stored job that has none.
    Adzuna/Remotive/Greenhouse/Jobicy never set this column at fetch time
    (only JSearch did, historically) — without this backfill, the
    experience gate's seniority-fallback path (core/matcher.py
    _job_band_index) treats every one of those jobs as fully unknown,
    which is more permissive than it needs to be for jobs whose title
    plainly says "Senior"/"Junior"/etc. Idempotent: already-filled rows
    are never touched."""
    from jobs.fetchers import infer_seniority_level

    supabase = get_supabase()
    updated = scanned = 0
    page_size = 200
    offset = 0
    try:
        while True:
            resp = (
                supabase.table("jobs")
                .select("id, title")
                .is_("seniority_level", "null")
                .order("collected_at", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = resp.data or []
            if not rows:
                break
            for row in rows:
                scanned += 1
                level = infer_seniority_level(row.get("title") or "")
                if level:
                    supabase.table("jobs").update(
                        {"seniority_level": level}
                    ).eq("id", row["id"]).execute()
                    updated += 1
            if len(rows) < page_size:
                break
            offset += page_size
        logger.info(f"✅ Seniority backfill: {updated}/{scanned} NULL-seniority jobs got an inferred level")
    except Exception as e:
        logger.error(f"❌ Seniority backfill failed after {updated}/{scanned}: {e}")


@router.post("/backfill-seniority")
async def backfill_seniority_now(background_tasks: BackgroundTasks, token: str = Query(..., description="Admin token")):
    """Infer seniority_level from title for existing jobs that don't have
    one, in the background. Run once after deploying the shared
    infer_seniority_level() (2026-07 experience-filtering fix); safe to
    re-run — only NULL rows are touched."""
    _require_admin(token)
    background_tasks.add_task(_audit, "seniority_backfill_triggered")
    background_tasks.add_task(_backfill_seniority)
    return {
        "status": "started",
        "message": "Backfilling seniority level from job titles in the background — check the server log for the summary line.",
    }


async def _classify_experience_ai() -> None:
    """
    One-time-ish CATCH-UP for the backlog: the free regex/title backfills
    above catch what a hand-written parser can, but some postings phrase
    requirements in ways no fixed pattern list can enumerate ("recent
    graduates welcome", "you'll mentor junior engineers") — this is the
    same core/job_classifier.classify_job AI fallback the daily pipeline
    already runs on a small batch automatically
    (core/pipeline_runner._classify_unknown_experience_jobs); this is the
    admin-triggered version for sweeping the CURRENT backlog rather than
    waiting on the daily trickle. Budget-checked per item (job_classify's
    own daily cap), so it naturally stops rather than needing its own
    limit — and stops the whole scan early after several consecutive
    empty results, since that's a strong signal the budget/provider is
    exhausted for today rather than worth scanning every remaining row.
    """
    # resolve_job_experience = application-page fetch + regex first (free
    # — many Adzuna listings state the requirement only on the company's
    # ATS page behind the apply link), then AI with the page as context.
    from core.job_classifier import resolve_job_experience

    supabase = get_supabase()
    updated = scanned = 0
    consecutive_empty = 0
    page_size = 100
    offset = 0
    exhausted = False
    try:
        while not exhausted:
            resp = (
                supabase.table("jobs")
                .select("id, title, description, source_url")
                .is_("required_experience_months", "null")
                .is_("seniority_level", "null")
                .order("collected_at", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = resp.data or []
            if not rows:
                break
            for row in rows:
                scanned += 1
                result = await resolve_job_experience(row)
                if result is None:
                    consecutive_empty += 1
                    if consecutive_empty >= 10:
                        logger.info(f"   Stopping AI classification catch-up after {consecutive_empty} consecutive empty results (budget/provider likely exhausted)")
                        exhausted = True
                        break
                    continue
                consecutive_empty = 0
                supabase.table("jobs").update(result).eq("id", row["id"]).execute()
                updated += 1
            if len(rows) < page_size:
                break
            offset += page_size
    except Exception as e:
        logger.error(f"❌ AI classification catch-up failed after {updated}/{scanned}: {e}")
        return
    logger.info(f"✅ AI classification catch-up: {updated}/{scanned} jobs got a value")


@router.post("/test-ai-providers")
async def test_ai_providers(token: str = Query(..., description="Admin token")):
    """
    Fire one tiny prompt at EACH configured AI provider individually and
    return per-provider ok/error — the diagnostic behind "this provider
    shows used == failed on the usage screen, but WHY?". The waterfall
    hides individual providers' errors by design (it just moves on); this
    surfaces the actual 401/404/429 text without needing server logs.
    Costs one budget-counted call per configured provider per click.
    Synchronous on purpose (unlike the pipeline/backfill triggers): the
    caller wants the results, and concurrent probes bound the wait to
    roughly one provider timeout.
    """
    _require_admin(token)
    _audit("ai_providers_probed")
    from core.ai import probe_all_providers
    return {"results": await probe_all_providers()}


async def _adzuna_probe(query: str, country: str, where: str | None) -> list[str]:
    """One live Adzuna page for a query — returns the RAW titles (before any
    filtering). Isolated so tests can stub it. Raises on HTTP failure."""
    import httpx

    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "what": query,
        "results_per_page": 50,
        "content-type": "application/json",
    }
    if where:
        params["where"] = where
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params=params)
        resp.raise_for_status()
        return [j.get("title", "") for j in resp.json().get("results", [])]


@router.get("/test-fetch")
async def test_fetch(
    token: str = Query(..., description="Admin token"),
    category: str = Query(..., description="Job category key or free text, e.g. hr_recruiter"),
    location: str = Query("", description="Optional city/country, resolved like a user preference"),
):
    """
    The "why did fetching find nothing for this category?" diagnostic —
    runs the EXACT same queries the pipeline would, against Adzuna live,
    and reports each stage separately: what Adzuna returned raw, what
    survived the title filter, and how many jobs the store already has
    for this category. Distinguishes "Adzuna has nothing for this
    search/city" from "our filter rejected everything" from "fetch works,
    the problem is downstream in matching" without needing server logs.
    Costs one budget-counted Adzuna call per query per click.
    """
    _require_admin(token)
    _audit("test_fetch", detail={"category": category, "location": location or None})

    from core.locations import ADZUNA_COUNTRIES
    from core.pipeline_runner import _queries_for_category
    from core.usage_guard import check_budget
    from jobs.fetchers import _title_matches, resolve_fetch_location

    queries_all = _queries_for_category(category)
    queries_used = queries_all[: settings.fetch_queries_per_category]
    loc = resolve_fetch_location(location) if location.strip() else None
    country = (loc or {}).get("country_code") or "in"
    where = (loc or {}).get("city")

    results = []
    for query in queries_used:
        row: dict = {
            "query": query,
            "adzuna_raw": None,
            "passed_title_filter": None,
            "sample_raw_titles": [],
            "sample_passing_titles": [],
            "error": None,
        }
        if not settings.adzuna_app_id or not settings.adzuna_app_key:
            row["error"] = "Adzuna API keys are not configured on this server."
        elif country not in ADZUNA_COUNTRIES:
            row["error"] = f"Adzuna has no endpoint for country '{country}' — the pipeline skips Adzuna for this location."
        elif not check_budget("adzuna", settings.adzuna_daily_limit):
            row["error"] = "Adzuna daily budget exhausted — counters reset at midnight."
        else:
            try:
                raw_titles = await _adzuna_probe(query, country, where)
                passing = [t for t in raw_titles if _title_matches(t, query)]
                row["adzuna_raw"] = len(raw_titles)
                row["passed_title_filter"] = len(passing)
                row["sample_raw_titles"] = raw_titles[:5]
                row["sample_passing_titles"] = passing[:5]
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"[:300]
        results.append(row)

    stored_count = None
    try:
        stored = (
            get_supabase()
            .table("jobs")
            .select("id", count="exact")
            .eq("search_category", category)
            .limit(1)
            .execute()
        )
        stored_count = getattr(stored, "count", None)
    except Exception:
        pass

    return {
        "category": category,
        "queries_used": queries_used,
        "queries_skipped": queries_all[settings.fetch_queries_per_category :],
        "location_input": location or None,
        "resolved_location": loc,
        "adzuna_country": country,
        "adzuna_where": where,
        "results": results,
        "jobs_stored_for_category": stored_count,
    }


@router.post("/classify-experience-ai")
async def classify_experience_ai_now(background_tasks: BackgroundTasks, token: str = Query(..., description="Admin token")):
    """AI fallback classification for jobs the free regex/title backfills
    couldn't parse, in the background. Bounded by job_classify's own
    daily budget cap (core/config.py); safe to re-run — only jobs still
    missing BOTH required_experience_months and seniority_level are
    touched."""
    _require_admin(token)
    background_tasks.add_task(_audit, "classify_experience_ai_triggered")
    background_tasks.add_task(_classify_experience_ai)
    return {
        "status": "started",
        "message": "Classifying remaining unknown-experience jobs with AI in the background — check the server log for the summary line.",
    }


@router.post("/run-pipeline")
async def run_pipeline_now(background_tasks: BackgroundTasks, token: str = Query(..., description="Admin token")):
    """Trigger a fetch+match run in the background. Returns immediately.

    _audit() runs as its OWN background task too, not inline — it's a
    synchronous, unbounded Supabase call, and this endpoint's whole
    contract (the GitHub Actions cron trigger calls it with a hard
    curl --max-time) is that nothing on the response path can stall it."""
    _require_admin(token)
    background_tasks.add_task(_audit, "pipeline_triggered")
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
    # ISO date/datetime after which the scheduler auto-clears both overrides
    # — a boost for a testing week shouldn't silently stay forever. None =
    # no expiry (and clears any previously-set expiry).
    override_expires_at: str | None = None


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

    expires_at = None
    if payload.override_expires_at:
        try:
            from datetime import datetime as _dt
            expires_at = _dt.fromisoformat(payload.override_expires_at.replace("Z", "+00:00")).isoformat()
        except ValueError:
            raise HTTPException(400, "override_expires_at must be an ISO date/datetime, e.g. 2026-07-20")

    update = {
        "resume_quota_override": clamp(payload.resume_quota_override, settings.resume_override_max),
        "job_count_override": clamp(payload.job_count_override, settings.job_override_max),
        "override_expires_at": expires_at,
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
        # override_expires_at is the newest column of the three — retry
        # without it so a pre-migration DB still accepts plain overrides.
        try:
            slim = {k: v for k, v in update.items() if k != "override_expires_at"}
            supabase.table("users").update(slim).eq("id", user_id).execute()
            update = slim
        except Exception:
            logger.error(f"   Override update failed for {user_id}: {e}")
            raise HTTPException(500, "Couldn't save overrides — the override columns may not be migrated yet.")

    _audit("overrides_changed", user_id, {"old": old, "new": update})
    # Echo the ceilings so the UI can SAY when a value was capped instead
    # of silently storing less than what the admin typed (live complaint:
    # "I can not increase the limit and it does not tell me how much").
    return {
        "status": "ok",
        **update,
        "caps": {
            "resume_quota": settings.resume_override_max,
            "job_count": settings.job_override_max,
        },
    }


# ── PDF failures — the diagnostic every "every resume shows Retry" report needs ──
@router.get("/pdf-failures")
async def recent_pdf_failures(token: str = Query(..., description="Admin token"), limit: int = Query(10, le=50)):
    """
    Most recent pdf_failed matches with their stored error text — the exact
    SQL query ('select ... from user_jobs where status=pdf_failed order by
    updated_at desc') as an endpoint, so diagnosing a PDF-render outage
    never requires direct Supabase access."""
    _require_admin(token)
    supabase = get_supabase()
    resp = (
        supabase.table("user_jobs")
        .select("id, user_id, status, pdf_error_message, updated_at, users(name, email)")
        .eq("status", "pdf_failed")
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []
    return {
        "count": len(rows),
        "failures": [
            {
                "match_id": r["id"],
                "user_id": r["user_id"],
                "user_name": (r.get("users") or {}).get("name"),
                "user_email": (r.get("users") or {}).get("email"),
                "error": r.get("pdf_error_message"),
                "updated_at": r.get("updated_at"),
            }
            for r in rows
        ],
    }


@router.get("/suspect-emails")
async def suspect_emails(token: str = Query(..., description="Admin token")):
    """
    Definitive scan: every stored user email run through the same
    core/email_validation.suggest_email_fix check /overview annotates
    rows with, but as its OWN standalone query — not embedded in the
    big /overview payload, so a client on stale-cached/paginated/scrolled
    table state (or simply not deployed past the commit that added
    email_suspect) still gets a straight, unambiguous answer to "does a
    bad email exist ANYWHERE in the users table right now." No .limit()
    — every row is checked, every time.
    """
    _require_admin(token)
    from core.email_validation import suggest_email_fix

    supabase = get_supabase()
    resp = supabase.table("users").select("id, name, email, is_active, created_at").execute()
    rows = resp.data or []
    flagged = []
    for r in rows:
        problem = suggest_email_fix(r.get("email") or "")
        if problem:
            flagged.append({
                "user_id": r["id"],
                "name": r.get("name") or "—",
                "email": r.get("email"),
                "is_active": bool(r.get("is_active")),
                "created_at": r.get("created_at"),
                "problem": problem,
            })
    return {"scanned": len(rows), "flagged": flagged}


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


# service -> the Settings field that must be non-empty for it to actually
# be in the AI waterfall / usable at all. A provider sitting at 0 usage is
# either "not needed yet" or "key missing" — those look identical from the
# usage number alone (a flat 0/500 with no failures either way), which is
# exactly what made the Groq outage take a code trace to diagnose instead
# of a glance at this screen. Services not in this map (e.g. resume_parse)
# aren't key-gated, so they're just omitted — no True/False to show.
def _raw_env_length(field_name: str) -> int | None:
    """
    The RAW os.environ value's length for a Settings field, bypassing
    pydantic — Settings._strip_wrapping_chars (config.py) strips
    whitespace/quote characters from every field on load, so a value that
    was e.g. a stray '\"' or a lone space would already read back as an
    empty string from `settings` even though something WAS actually set
    on the container. Comparing raw vs validated length is what tells
    "never configured" apart from "configured with garbage that got
    stripped to nothing" — pydantic-settings matches env vars
    case-insensitively, so this does too. Returns None when the variable
    isn't present in the environment at all (vs present-but-empty, 0).
    """
    target = field_name.upper()
    for key, value in os.environ.items():
        if key.upper() == target:
            return len(value)
    return None


_KEY_SETTINGS: dict[str, str] = {
    "gemini_generate": "gemini_api_key",
    "gemini_embed": "gemini_api_key",
    "groq": "groq_api_key",
    "openrouter": "openrouter_api_key",
    "github_models": "github_models_token",
    "mistral": "mistral_api_key",
    "cohere": "cohere_api_key",
    "adzuna": "adzuna_app_key",
    "jsearch": "jsearch_api_key",
    "openai": "openai_api_key",
    "resend": "resend_api_key",
}


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
            .select(f"{base_user_fields}, resume_quota_override, job_count_override, override_expires_at")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
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
    # email_suspect: flags stored addresses that would bounce (typo'd
    # domains like gmial.com) — Gmail bounces asynchronously so
    # email_logs shows 'sent' for these; this is the only place a bad
    # stored address becomes visible without waiting for a bounce email.
    from core.email_validation import suggest_email_fix
    user_rows = [
        {
            "id": u["id"],
            "name": u.get("name") or "—",
            "email": u.get("email") or "—",
            "email_suspect": suggest_email_fix(u.get("email") or ""),
            "joined_at": u.get("created_at"),
            "job_category": u.get("job_category") or "—",
            "experience_level": u.get("experience_level") or "—",
            "is_active": bool(u.get("is_active")),
            "has_resume": bool(u.get("resume_file_path")),
            "dashboard_token": generate_dashboard_token(u["id"]),
            "resume_quota_override": u.get("resume_quota_override"),
            "job_count_override": u.get("job_count_override"),
            "override_expires_at": u.get("override_expires_at"),
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

    # `failed` = the waterfall's '{provider}_fail' diagnostic bucket
    # (core/ai.py) — Gemini's generation budget bucket is 'gemini_generate'
    # but its provider name (hence fail bucket) is plain 'gemini'.
    api_usage = [
        {
            **svc,
            "used": used.get(svc["service"], 0),
            "failed": used.get(f"{svc['service'].removesuffix('_generate')}_fail", 0),
            **(
                {
                    "key_configured": bool(getattr(settings, _KEY_SETTINGS[svc["service"]], "")),
                    # Validated (post-strip) length — 0 even if the raw env
                    # var had content that got stripped down to nothing.
                    "key_length": len(getattr(settings, _KEY_SETTINGS[svc["service"]], "") or ""),
                    # Raw os.environ length — None means the variable isn't
                    # present on this container AT ALL (a real "never set"
                    # or wrong name); 0 means present but empty; a
                    # nonzero value here alongside key_length=0 means
                    # SOMETHING was saved but our own whitespace/quote
                    # stripping ate all of it.
                    "raw_env_length": _raw_env_length(_KEY_SETTINGS[svc["service"]]),
                }
                if svc["service"] in _KEY_SETTINGS
                else {}
            ),
        }
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
        # provider is a newer column — retry the select without it so an
        # un-run migration degrades to history-without-provider, not no
        # history at all.
        base_cols = "user_id, email_address, type, status, subject, error_message, sent_at"
        try:
            logs_resp = (
                supabase.table("email_logs")
                .select(f"{base_cols}, provider")
                .order("sent_at", desc=True)
                .limit(50)
                .execute()
            )
        except Exception:
            logs_resp = (
                supabase.table("email_logs")
                .select(base_cols)
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
                "provider": row.get("provider"),
                "error_message": row.get("error_message"),
                "sent_at": row.get("sent_at"),
            }
            for row in (logs_resp.data or [])
        ]
    except Exception:
        pass

    # PDF engine diagnostic — same raw-vs-validated pattern as the API-key
    # checks above: settings.pdf_engine is what the app is ACTUALLY using
    # (post-strip, post-default); raw_env_length distinguishes "PDF_ENGINE
    # isn't set at all on this container" (None) from "set but empty" (0)
    # from "set correctly" (nonzero). This is exactly the class of bug that
    # broke PDF rendering silently after the Render->Coolify/VPS migration —
    # visible here at a glance instead of requiring a support thread.
    pdf_engine_diagnostic = {
        "configured": settings.pdf_engine,
        "raw_env_length": _raw_env_length("pdf_engine"),
    }

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
        "pdf_engine": pdf_engine_diagnostic,
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
