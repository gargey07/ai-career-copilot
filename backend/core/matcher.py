"""
Matching Engine — Local Vector Similarity Matching
───────────────────────────────────────────────────
Uses pgvector cosine similarity in PostgreSQL to match
jobs to users without any AI calls. Fast and free.

Flow:
  1. Embed user's resume text (once, cached in DB)
  2. Query jobs table using cosine similarity
  3. Prefer jobs the user hasn't been shown before (freshness)
  4. Return top N matches for the user
  5. Store results in user_jobs table

Freshness: the free job sources return largely the same jobs day over
day, so without dedup a user's "new matches every morning" is really the
same handful of jobs on repeat — that breaks the core promise. Matching
overfetches candidates and prioritizes ones the user hasn't seen; if the
job pool is too small to stay fully fresh, it backfills with the jobs
shown longest ago rather than returning an empty digest.

Run standalone to test:
    python core/matcher.py
"""
from __future__ import annotations
import asyncio
import logging
from datetime import date

from core.ai import get_ai_provider
from core.config import get_settings
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()


async def embed_user_profile(user: dict) -> list[float]:
    """
    Generate an embedding vector for a user's resume + preferences.
    Combines resume text + target roles + experience for best matching.
    """
    ai = get_ai_provider()

    profile_text = f"""
    Target Roles: {', '.join(user.get('target_roles', []))}
    Experience Level: {user.get('experience_level', 'mid')}
    Location Preference: {', '.join(user.get('preferred_locations', []))}
    Remote Preference: {user.get('remote_preference', 'any')}

    Resume:
    {user.get('resume_text', '')}
    """.strip()

    return await ai.embed_text(profile_text)


async def _get_seen_job_ids(supabase, user_id: str) -> dict[str, str]:
    """job_id -> most recent digest_date it was shown to this user. Best-effort:
    a failure here just disables freshness prioritization for this run, it
    never blocks matching."""
    try:
        resp = supabase.table("user_jobs").select("job_id, digest_date").eq("user_id", user_id).execute()
    except Exception as e:
        logger.warning(f"   Couldn't load match history for freshness ({e}) — skipping dedup this run.")
        return {}

    seen: dict[str, str] = {}
    for row in resp.data or []:
        job_id, shown = row.get("job_id"), row.get("digest_date")
        if job_id and shown and (job_id not in seen or shown > seen[job_id]):
            seen[job_id] = shown
    return seen


def _prioritize_fresh(jobs: list[dict], seen: dict[str, str], limit: int) -> list[dict]:
    """
    `jobs` must already be sorted best-match-first. Prefer jobs the user
    hasn't been shown before; if there aren't `limit` fresh ones (small job
    pool), backfill with previously-shown jobs ordered oldest-shown-first —
    a repeat is better than an empty digest, and the least-recent repeat is
    better than yesterday's exact list again.
    """
    if not seen:
        return jobs[:limit]

    fresh = [j for j in jobs if j.get("id") not in seen]
    if len(fresh) >= limit:
        return fresh[:limit]

    stale = [j for j in jobs if j.get("id") in seen]
    stale.sort(key=lambda j: seen.get(j.get("id"), ""))
    return (fresh + stale)[:limit]


# How many extra candidates to pull before filtering for freshness — cheap
# (a DB query, not an AI call), so overfetching is basically free.
_OVERFETCH_MULTIPLIER = 5
_OVERFETCH_CAP = 100


async def match_jobs_for_user(user_id: str, limit: int = None) -> list[dict]:
    """
    Find the top N jobs matching a user's profile using vector similarity,
    preferring ones the user hasn't seen before.

    Args:
        user_id: UUID of the user
        limit: Max jobs to return (defaults to MAX_JOBS_PER_USER in settings)

    Returns:
        List of matched jobs with their match_score
    """
    limit = limit or settings.max_jobs_per_user
    supabase = get_supabase()

    # 1. Get user profile
    user_resp = supabase.table("users").select("*").eq("id", user_id).single().execute()
    if not user_resp.data:
        logger.error(f"❌ User {user_id} not found")
        return []

    user = user_resp.data
    logger.info(f"🎯 Matching jobs for user: {user.get('name', user_id)}")

    seen = await _get_seen_job_ids(supabase, user_id)
    overfetch = min(limit * _OVERFETCH_MULTIPLIER, _OVERFETCH_CAP)

    # 2. Try AI vector matching (Gemini embedding + pgvector). Any failure here
    #    — no Gemini key, budget exhausted, missing pgvector function, no job
    #    embeddings yet — degrades gracefully to keyword matching so jobs still
    #    appear on the dashboard at $0.
    try:
        if user.get("resume_embedding"):
            user_embedding = user["resume_embedding"]
        else:
            user_embedding = await embed_user_profile(user)
            supabase.table("users").update({"resume_embedding": user_embedding}).eq("id", user_id).execute()

        matched = supabase.rpc("match_jobs", {"query_embedding": user_embedding, "match_count": overfetch}).execute()
        jobs = matched.data or []
        if jobs:
            fresh_jobs = _prioritize_fresh(jobs, seen, limit)
            logger.info(f"   Found {len(jobs)} candidates (vector), {len(fresh_jobs)} after freshness filter")
            return fresh_jobs
        logger.info("   Vector match returned nothing — falling back to keyword match")
    except Exception as e:
        logger.warning(f"⚠️  Vector matching unavailable ({e}) — falling back to keyword match")

    # 3. Keyword fallback — no AI required.
    recent = (
        supabase.table("jobs")
        .select("*")
        .order("collected_at", desc=True)
        .limit(300)
        .execute()
    )
    return keyword_match(user, recent.data or [], limit, seen=seen)


def keyword_match(user: dict, jobs: list[dict], limit: int, seen: dict[str, str] | None = None) -> list[dict]:
    """
    Score jobs by overlap between the user's roles/skills/tools/category and each
    job's title + description. Pure text — no embeddings, no AI. Used when vector
    matching isn't available. Returns the top `limit` jobs with a match_score,
    preferring ones the user hasn't seen before (see _prioritize_fresh).
    """
    import re as _re

    seen = seen or {}
    terms: set[str] = set()
    for field in ("target_roles", "skills", "tools"):
        for value in (user.get(field) or []):
            for word in _re.findall(r"[a-z0-9+#.]+", str(value).lower()):
                if len(word) >= 2:
                    terms.add(word)
    for word in _re.findall(r"[a-z0-9+#.]+", str(user.get("job_category") or "").replace("_", " ").lower()):
        if len(word) >= 2:
            terms.add(word)

    if not terms:
        # Nothing to match on — surface the freshest jobs so the dashboard isn't empty.
        return _prioritize_fresh([{**job, "match_score": 0.3} for job in jobs], seen, limit)

    def words(text: str) -> set[str]:
        return set(_re.findall(r"[a-z0-9+#.]+", str(text).lower()))

    scored: list[dict] = []
    for job in jobs:
        title_words = words(job.get("title", ""))
        body_words = title_words | words(job.get("description", ""))
        # Whole-word matching (avoids "design" matching "designer", etc.).
        hits = sum(1 for t in terms if t in body_words)
        if hits:
            title_hits = sum(1 for t in terms if t in title_words)
            raw = (hits + title_hits * 2) / (len(terms) + 2)
            scored.append({**job, "match_score": round(min(0.98, 0.5 + raw), 4)})

    scored.sort(key=lambda j: j["match_score"], reverse=True)
    if scored:
        return _prioritize_fresh(scored, seen, limit)
    return _prioritize_fresh([{**job, "match_score": 0.3} for job in jobs], seen, limit)


async def store_matches(user_id: str, matched_jobs: list[dict]) -> int:
    """
    Store matched jobs in the user_jobs table.
    Only stores today's digest — skips if already processed.
    """
    supabase = get_supabase()
    today = date.today().isoformat()

    rows = []
    for rank, job in enumerate(matched_jobs, start=1):
        # The replaced match_jobs SQL function (migration_v2_1.sql) returns
        # percentage scores (0–100) while everything else here uses 0–1 —
        # normalize so stored scores are always 0–1 regardless of which
        # version of the function the database has.
        score = job.get("match_score", 0.0) or 0.0
        if score > 1:
            score = score / 100.0
        rows.append({
            "user_id": user_id,
            "job_id": job["id"],
            "match_score": round(min(score, 1.0), 4),
            "rank": rank,
            "digest_date": today,
            "status": "matched",
        })

    if not rows:
        return 0

    try:
        resp = (
            supabase.table("user_jobs")
            .upsert(rows, on_conflict="user_id,job_id,digest_date", ignore_duplicates=True)
            .execute()
        )
        count = len(resp.data) if resp.data else 0
        logger.info(f"✅ Stored {count} job matches for user {user_id}")
        return count
    except Exception as e:
        logger.error(f"❌ Failed to store matches: {e}")
        raise


async def run_matching_for_all_users() -> dict:
    """Run job matching for every active user. Called by the daily pipeline."""
    supabase = get_supabase()

    users_resp = supabase.table("users").select("id, name").eq("is_active", True).execute()
    users = users_resp.data or []

    logger.info(f"👥 Running matching for {len(users)} active users")

    total_matches = 0
    for user in users:
        try:
            matches = await match_jobs_for_user(user["id"])
            stored = await store_matches(user["id"], matches)
            total_matches += stored
        except Exception as e:
            logger.error(f"❌ Matching failed for user {user.get('name', user['id'])}: {e}")

    return {"users_processed": len(users), "total_matches": total_matches}


# ── pgvector SQL Function (run once in Supabase) ──────────────────────────────
PGVECTOR_MATCH_FUNCTION = """
-- Run this ONCE in Supabase SQL Editor to enable vector matching
CREATE OR REPLACE FUNCTION match_jobs(
  query_embedding vector(768),
  match_count     int DEFAULT 10
)
RETURNS TABLE (
  id          uuid,
  title       text,
  company     text,
  location    text,
  description text,
  source_url  text,
  is_remote   boolean,
  posted_at   timestamptz,
  match_score float
)
LANGUAGE sql STABLE AS $$
  SELECT
    id, title, company, location, description, source_url, is_remote, posted_at,
    1 - (embedding <=> query_embedding) AS match_score
  FROM jobs
  WHERE embedding IS NOT NULL
    AND collected_at > NOW() - INTERVAL '7 days'
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;
"""


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    print("📋 pgvector SQL function to run in Supabase:\n")
    print(PGVECTOR_MATCH_FUNCTION)
    print("\n" + "─" * 60)
    print("Run `python core/matcher.py` with a real user_id to test matching.")
