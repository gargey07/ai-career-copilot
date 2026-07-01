"""
Matching Engine — Local Vector Similarity Matching
───────────────────────────────────────────────────
Uses pgvector cosine similarity in PostgreSQL to match
jobs to users without any AI calls. Fast and free.

Flow:
  1. Embed user's resume text (once, cached in DB)
  2. Query jobs table using cosine similarity
  3. Return top N matches for the user
  4. Store results in user_jobs table

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


async def match_jobs_for_user(user_id: str, limit: int = None) -> list[dict]:
    """
    Find the top N jobs matching a user's profile using vector similarity.

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

    # 2. Generate user embedding (or use cached one)
    if user.get("resume_embedding"):
        logger.info("   Using cached resume embedding")
        user_embedding = user["resume_embedding"]
    else:
        logger.info("   Generating new resume embedding...")
        user_embedding = await embed_user_profile(user)

        # Cache the embedding in the users table
        supabase.table("users").update(
            {"resume_embedding": user_embedding}
        ).eq("id", user_id).execute()

    # 3. Query top matching jobs using pgvector cosine similarity
    # This runs entirely in PostgreSQL — zero AI cost!
    try:
        matched = supabase.rpc(
            "match_jobs",
            {
                "query_embedding": user_embedding,
                "match_count": limit,
            }
        ).execute()

        jobs = matched.data or []
        logger.info(f"   Found {len(jobs)} matching jobs")
        return jobs

    except Exception as e:
        # Fallback: if pgvector isn't set up yet, return recent jobs
        logger.warning(f"⚠️  pgvector matching failed ({e}), falling back to recency sort")
        recent = (
            supabase.table("jobs")
            .select("*")
            .order("collected_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [{"match_score": 0.5, **job} for job in (recent.data or [])]


async def store_matches(user_id: str, matched_jobs: list[dict]) -> int:
    """
    Store matched jobs in the user_jobs table.
    Only stores today's digest — skips if already processed.
    """
    supabase = get_supabase()
    today = date.today().isoformat()

    rows = []
    for rank, job in enumerate(matched_jobs, start=1):
        rows.append({
            "user_id": user_id,
            "job_id": job["id"],
            "match_score": round(job.get("match_score", 0.0), 4),
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
