"""
Pipeline Runner — the full daily chain
──────────────────────────────────────
fetch → embed (best-effort) → match → optimize resumes → render PDFs →
send morning digest. Populates `user_jobs` (the dashboard) and sends the
daily email.

Every stage past matching degrades gracefully (see the failure-mode
contract in docs/AI_CAREER_INTELLIGENCE_ENGINE.md): no Gemini key or
budget → matches ship without tailored resumes; no Playwright browser →
matches ship without PDFs; no email provider → dashboard-only. A stage
failing for one user never blocks the next user.

Kept separate from pipeline.py so importing it never triggers
pipeline.py's file-logging setup.
"""
from __future__ import annotations
import logging

from database.supabase_client import get_supabase
from jobs.fetchers import run_all_fetchers
from core.config import get_settings
from core.skill_maps import get_search_queries, JOB_CATEGORIES
from core.matcher import run_matching_for_all_users

logger = logging.getLogger(__name__)
settings = get_settings()


async def _embed_unembedded_jobs(batch_size: int = 50) -> int:
    """
    Best-effort: embed jobs that don't have an embedding yet. Silently no-ops
    if no AI provider is configured or the budget is exhausted — the matcher
    falls back to keyword matching in that case.
    """
    supabase = get_supabase()
    try:
        from core.ai import get_ai_provider
        ai = get_ai_provider()
    except Exception as e:
        logger.info(f"   Skipping embeddings (no AI provider available: {e})")
        return 0

    resp = (
        supabase.table("jobs")
        .select("id, title, company, description")
        .is_("embedding", "null")
        .limit(batch_size)
        .execute()
    )
    jobs = resp.data or []
    count = 0
    for job in jobs:
        try:
            text = f"{job['title']} at {job.get('company', '')}. {(job.get('description') or '')[:1000]}"
            embedding = await ai.embed_text(text)
            supabase.table("jobs").update({"embedding": embedding}).eq("id", job["id"]).execute()
            count += 1
        except Exception as e:
            # First failure (missing key / budget) — stop hammering; keyword match covers us.
            logger.info(f"   Stopping embeddings after {count} (reason: {e})")
            break
    return count


async def _classify_unknown_experience_jobs(batch_size: int = 30) -> int:
    """
    AI fallback for jobs the free, instant pass (jobs/fetchers.py's
    experience_months_from_text + infer_seniority_level) came up
    completely empty on — phrasing like "recent graduates welcome" that
    no regex/keyword list can enumerate. Only ever targets that residual
    bucket (WHERE both columns are still NULL), so it's a fallback, not a
    replacement for the free pass. Best-effort and budget-capped, same
    degrade-gracefully contract as _embed_unembedded_jobs above — stops
    quietly (not an error) the moment the daily job_classify budget or
    the AI provider itself is unavailable; the matcher's existing
    "unknown data passes" policy covers the rest.
    """
    supabase = get_supabase()
    try:
        from core.job_classifier import classify_job
    except Exception as e:
        logger.info(f"   Skipping AI experience classification (unavailable: {e})")
        return 0

    resp = (
        supabase.table("jobs")
        .select("id, title, description")
        .is_("required_experience_months", "null")
        .is_("seniority_level", "null")
        .limit(batch_size)
        .execute()
    )
    jobs = resp.data or []
    count = 0
    for job in jobs:
        # classify_job checks the daily budget BEFORE making any AI call,
        # so once it's exhausted every remaining job in this batch
        # returns None near-instantly (no wasted spend) — skip and move
        # on rather than breaking the loop, so one job's unparseable
        # output (a real but separate failure mode) doesn't cost the rest
        # of the batch their fair shot.
        result = await classify_job(job)
        if result is None:
            continue
        try:
            supabase.table("jobs").update(result).eq("id", job["id"]).execute()
            count += 1
        except Exception as e:
            logger.warning(f"   Couldn't write AI classification for job {job['id']} ({e}) — continuing.")
    if jobs:
        logger.info(f"   🧠 AI experience classification: {count}/{len(jobs)} jobs got a value")
    return count


def _queries_for_category(category: str) -> list[str]:
    """Known category -> its curated search queries; free-text -> the text itself."""
    if category in JOB_CATEGORIES:
        return get_search_queries(category)
    return [category] if category else [""]


async def generate_resumes_for_user(user_id: str) -> dict:
    """
    Optimizer → PDF for one user's already-matched jobs. No email — this
    is the reusable half of delivery, shared by the full nightly pipeline
    (which continues on to email) and instant-first-match on signup
    (which shouldn't send an email, just wants the dashboard populated
    quickly — see api/routes/resumes.py). Each step is best-effort; a
    failure downgrades the output, never raises.
    """
    stats = {"resumes": 0, "pdfs": 0}

    try:
        from core.optimizer import run_optimizer_for_user
        stats["resumes"] = await run_optimizer_for_user(user_id)
    except Exception as e:
        logger.warning(f"   Optimizer skipped for {user_id}: {e}")

    try:
        from core.pdf_generator import run_pdf_generator_for_user
        stats["pdfs"] = await run_pdf_generator_for_user(user_id)
    except Exception as e:
        # Most common cause: Playwright's Chromium isn't installed on the
        # server (render.yaml build installs it; first deploy may lag).
        logger.warning(f"   PDF generation skipped for {user_id}: {e}")

    return stats


async def _run_delivery_for_user(user_id: str) -> dict:
    """Phase 3 for one user: tailored resumes → PDFs → digest email."""
    stats = await generate_resumes_for_user(user_id)
    stats["emailed"] = False

    try:
        from core.email_sender import send_morning_digest
        stats["emailed"] = await send_morning_digest(user_id)
    except Exception as e:
        logger.warning(f"   Digest email skipped for {user_id}: {e}")

    return stats


async def send_admin_alert(subject: str, body: str) -> None:
    """
    Email the founder when a pipeline run fails outright (not per-user
    degradations — those are logged and degrade gracefully by design).
    Capped at a few per day via the usage-guard table so a failure that
    recurs every scheduler tick can't flood the inbox.
    """
    try:
        from core.email_sender import _send_email
        from core.usage_guard import check_budget

        if not check_budget("admin_alerts", 5):
            logger.warning("   Admin-alert daily cap reached — suppressing further alerts today.")
            return
        html = f"<pre style='font-family:monospace;white-space:pre-wrap'>{body}</pre>"
        await _send_email(settings.founder_email, f"[AI Career Copilot] {subject}", html, unsubscribe_url="")
        logger.info(f"   🚨 Admin alert sent: {subject}")
    except Exception as e:
        # Alerting must never take the pipeline down with it.
        logger.error(f"   Couldn't send admin alert ({subject}): {e}")


# Each extra preferred location multiplies fetch volume; two per user keeps
# the (category × location × query) fan-out inside the free-tier API budgets.
MAX_FETCH_LOCATIONS_PER_USER = 2


def _fetch_targets(users: list[dict]) -> list[tuple[str, dict | None]]:
    """
    Unique (category, location) fetch pairs across all active users. Every
    user contributes their primary job_category AND their
    secondary_categories ("also open to") — without fetching those too,
    a secondary category could only ever match jobs other users' fetches
    happened to pool. A user with no resolvable preferred_locations gets
    (category, None) — the historical India default. Pairs are deduped by
    category+country+city so ten London users cost one fetch, not ten.
    """
    from jobs.fetchers import resolve_fetch_location

    targets: dict[tuple[str, str], tuple[str, dict | None]] = {}
    for u in users:
        categories = [(u.get("job_category") or "").strip() or "ui_ux_designer"]
        categories += [c.strip() for c in (u.get("secondary_categories") or []) if c and c.strip()]
        resolved = []
        for raw in (u.get("preferred_locations") or [])[:MAX_FETCH_LOCATIONS_PER_USER * 2]:
            loc = resolve_fetch_location(raw)
            if loc:
                resolved.append(loc)
            if len(resolved) >= MAX_FETCH_LOCATIONS_PER_USER:
                break
        for category in dict.fromkeys(categories):  # order-preserving dedup
            for loc in resolved or [None]:
                key = (category, f"{loc['country_code']}|{(loc.get('city') or '').lower()}" if loc else "")
                targets.setdefault(key, (category, loc))
    return list(targets.values())


async def run_fetch_and_match_jobs_only() -> dict:
    """Fetch → embed → match for all active users. No resumes/PDFs/email —
    the delivery half runs separately, per user, at their chosen digest slot."""
    supabase = get_supabase()
    # secondary_categories is a newer column — degrade progressively so an
    # un-run migration costs the feature, never the whole fetch phase.
    try:
        users = supabase.table("users").select("id, job_category, preferred_locations, secondary_categories").eq("is_active", True).execute().data or []
    except Exception:
        try:
            users = supabase.table("users").select("id, job_category, preferred_locations").eq("is_active", True).execute().data or []
        except Exception:
            users = supabase.table("users").select("id, job_category").eq("is_active", True).execute().data or []
    categories = sorted({(u.get("job_category") or "").strip() or "ui_ux_designer" for u in users})

    total_fetched = 0
    for category, location in _fetch_targets(users):
        for query in _queries_for_category(category)[: settings.fetch_queries_per_category]:
            try:
                total_fetched += await run_all_fetchers(query=query, category=category, location=location)
            except Exception as e:
                logger.error(f"   Fetch failed for '{category}' / '{query}': {e}")

    embedded = await _embed_unembedded_jobs()
    experience_classified = await _classify_unknown_experience_jobs()
    match_result = await run_matching_for_all_users()
    return {
        "categories": categories,
        "jobs_fetched": total_fetched,
        "jobs_embedded": embedded,
        "jobs_experience_classified": experience_classified,
        **match_result,
    }


async def run_fetch_and_match() -> dict:
    """The full pipeline in one shot: fetch → embed → match → optimize →
    PDF → email for every active user. Used by the manual admin trigger;
    the scheduler uses the split halves to honor per-user digest slots."""
    supabase = get_supabase()
    fetch_stats = await run_fetch_and_match_jobs_only()
    users = supabase.table("users").select("id").eq("is_active", True).execute().data or []

    resumes = pdfs = emails = 0
    for user in users:
        delivery = await _run_delivery_for_user(user["id"])
        resumes += delivery["resumes"]
        pdfs += delivery["pdfs"]
        emails += 1 if delivery["emailed"] else 0

    stats = {
        **fetch_stats,
        "resumes_optimized": resumes,
        "pdfs_generated": pdfs,
        "digests_emailed": emails,
    }
    logger.info(f"🏁 Pipeline complete: {stats}")
    return stats
