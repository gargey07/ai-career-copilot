"""
Pipeline Runner — fetch + match (Phase 1)
─────────────────────────────────────────
The lightweight core of the daily pipeline: pull jobs from the (free)
sources for each active user's category, embed them if an AI provider is
available, then match jobs to users (vector, or keyword fallback). This
populates `user_jobs`, which is what the dashboard reads.

Deliberately does NOT do resume optimization / PDF / email (those need
Gemini + Playwright + an email provider). Kept separate from pipeline.py
so importing it never triggers pipeline.py's file-logging setup.
"""
from __future__ import annotations
import logging

from database.supabase_client import get_supabase
from jobs.fetchers import run_all_fetchers
from core.skill_maps import get_search_queries, JOB_CATEGORIES
from core.matcher import run_matching_for_all_users

logger = logging.getLogger(__name__)


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


def _queries_for_category(category: str) -> list[str]:
    """Known category -> its curated search queries; free-text -> the text itself."""
    if category in JOB_CATEGORIES:
        return get_search_queries(category)
    return [category] if category else [""]


async def run_fetch_and_match() -> dict:
    """Fetch jobs for every active user's category, embed (best-effort), then match."""
    supabase = get_supabase()
    users = supabase.table("users").select("job_category").eq("is_active", True).execute().data or []
    categories = sorted({(u.get("job_category") or "").strip() or "ui_ux_designer" for u in users})

    total_fetched = 0
    for category in categories:
        for query in _queries_for_category(category)[:1]:  # one query per category to stay light
            try:
                total_fetched += await run_all_fetchers(query=query)
            except Exception as e:
                logger.error(f"   Fetch failed for '{category}' / '{query}': {e}")

    embedded = await _embed_unembedded_jobs()
    match_result = await run_matching_for_all_users()

    stats = {
        "categories": categories,
        "jobs_fetched": total_fetched,
        "jobs_embedded": embedded,
        **match_result,
    }
    logger.info(f"🏁 Fetch+match complete: {stats}")
    return stats
