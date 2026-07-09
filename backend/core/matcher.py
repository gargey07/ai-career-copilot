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
import re
from datetime import date

from core.ai import get_ai_provider
from core.config import get_settings
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", str(text or "").lower()))


def _user_terms(user: dict) -> set[str]:
    """Broad term set (roles + skills + tools + category) used for keyword
    SCORING — how well a job's text matches this user, once it's already
    known to be in the right profession."""
    terms: set[str] = set()
    for field in ("target_roles", "skills", "tools"):
        for value in (user.get(field) or []):
            terms |= {w for w in _tokenize(value) if len(w) >= 2}
    terms |= {w for w in _tokenize(str(user.get("job_category") or "").replace("_", " ")) if len(w) >= 2}
    return terms


def _category_terms(user: dict) -> set[str]:
    """Narrower term set (category + target roles ONLY, no skills/tools)
    used for category RELEVANCE gating — deliberately excludes skills/
    tools because those are too generic and are exactly why a Fullstack
    Developer's "javascript"/"api" skills could loosely match a UI/UX
    Designer job description under the broader _user_terms set."""
    terms: set[str] = set()
    terms |= {w for w in _tokenize(str(user.get("job_category") or "").replace("_", " ")) if len(w) >= 2}
    for role in (user.get("target_roles") or []):
        terms |= {w for w in _tokenize(role) if len(w) >= 2}
    return terms


def _category_relevant(job: dict, user_category: str, category_terms: set[str]) -> bool:
    """
    True when `job` belongs to the user's profession. Prefers the exact
    search_category tag stamped at fetch time (jobs/fetchers.py); jobs
    fetched before that column existed, or returned by the vector-search
    RPC (which doesn't carry the tag), fall back to a text check — at
    least one category/target-role term in the title, or two in the
    description — rather than being silently excluded or blindly included.
    """
    tag = job.get("search_category")
    if tag:
        return tag == user_category
    if not category_terms:
        return True  # nothing to check against — don't blanket-exclude
    title_words = _tokenize(job.get("title", ""))
    if category_terms & title_words:
        return True
    desc_words = _tokenize(job.get("description", ""))
    return len(category_terms & desc_words) >= 2


# Even a category-relevant keyword match can be pure noise (one incidental
# term overlap) — this is the formula's floor for hits >= 1, so 0.55
# meaningfully drops the weakest matches instead of padding the digest
# with them.
MIN_KEYWORD_SCORE = 0.55

# Score multiplier for jobs whose title overlaps a job the user marked
# "not relevant (wrong role)" — deliberately harsh enough to push most
# such candidates under MIN_KEYWORD_SCORE rather than merely reordering.
_WRONG_ROLE_DEMOTION = 0.5


async def _load_relevance_penalties(supabase, user_id: str) -> dict:
    """
    Personalization signals from "Not relevant" job feedback (job_feedback
    columns; written by POST .../job-feedback). Returns:
      {"exclude_companies": set[str lowercase],   # reason='company'
       "demote_title_tokens": set[str]}           # reason='wrong_role'
    Best-effort — any failure (including unmigrated columns) returns empty
    penalties and matching proceeds unpersonalized.
    """
    empty = {"exclude_companies": set(), "demote_title_tokens": set()}
    try:
        resp = (
            supabase.table("user_jobs")
            .select("job_feedback_reason, jobs(title, company)")
            .eq("user_id", user_id)
            .eq("job_feedback", "not_relevant")
            .execute()
        )
    except Exception as e:
        logger.info(f"   No relevance penalties loaded ({e}) — matching unpersonalized.")
        return empty

    penalties = {"exclude_companies": set(), "demote_title_tokens": set()}
    for row in resp.data or []:
        job = row.get("jobs") or {}
        reason = row.get("job_feedback_reason") or ""
        if reason == "company" and job.get("company"):
            penalties["exclude_companies"].add(str(job["company"]).strip().lower())
        elif reason == "wrong_role" and job.get("title"):
            penalties["demote_title_tokens"] |= {w for w in _tokenize(job["title"]) if len(w) >= 3}
    return penalties


def _apply_relevance_penalties(jobs: list[dict], penalties: dict) -> list[dict]:
    """Drop excluded-company jobs; halve the score of wrong-role lookalikes.
    Jobs must carry match_score already; order is re-sorted afterward by
    the caller's pipeline (scored sort / _prioritize_fresh)."""
    if not penalties["exclude_companies"] and not penalties["demote_title_tokens"]:
        return jobs
    result = []
    for job in jobs:
        company = str(job.get("company") or "").strip().lower()
        if company and company in penalties["exclude_companies"]:
            continue
        if penalties["demote_title_tokens"]:
            title_tokens = {w for w in _tokenize(job.get("title", "")) if len(w) >= 3}
            # Two shared meaningful title words = same kind of role the
            # user already rejected; one shared word ("senior", "remote"
            # never make it here due to length/meaning, but "developer"
            # alone shouldn't tank everything) is not enough.
            if len(title_tokens & penalties["demote_title_tokens"]) >= 2:
                job = {**job, "match_score": round((job.get("match_score") or 0) * _WRONG_ROLE_DEMOTION, 4)}
        result.append(job)
    return result


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
    penalties = await _load_relevance_penalties(supabase, user_id)
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
            # The match_jobs SQL function's fixed column list doesn't
            # include search_category, so a high cosine-similarity score
            # alone can still be the wrong profession entirely (e.g. a
            # UI/UX Designer job scoring 74% for a Fullstack Developer).
            # Batch-fetch the tag for these candidates and filter by it.
            user_category = (user.get("job_category") or "").strip()
            category_terms = _category_terms(user)
            job_ids = [j["id"] for j in jobs if j.get("id")]
            cat_by_id: dict[str, str | None] = {}
            if job_ids:
                try:
                    cat_resp = supabase.table("jobs").select("id, search_category").in_("id", job_ids).execute()
                    cat_by_id = {row["id"]: row.get("search_category") for row in (cat_resp.data or [])}
                except Exception as e:
                    logger.warning(f"   Couldn't load search_category for candidates ({e}) — skipping category filter this run.")
                    cat_by_id = None  # signals "don't filter" below

            if cat_by_id is not None:
                for j in jobs:
                    j["search_category"] = cat_by_id.get(j.get("id"))
                relevant = [j for j in jobs if _category_relevant(j, user_category, category_terms)]
            else:
                relevant = jobs

            relevant = _apply_relevance_penalties(relevant, penalties)
            relevant.sort(key=lambda j: j.get("match_score") or 0, reverse=True)

            if relevant:
                fresh_jobs = _prioritize_fresh(relevant, seen, limit)
                logger.info(
                    f"   Found {len(jobs)} candidates (vector), {len(relevant)} category-relevant, "
                    f"{len(fresh_jobs)} after freshness filter"
                )
                return fresh_jobs
            logger.info("   Vector match had candidates but none were category-relevant — falling back to keyword match")
        else:
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
    return keyword_match(user, recent.data or [], limit, seen=seen, penalties=penalties)


def keyword_match(
    user: dict, jobs: list[dict], limit: int,
    seen: dict[str, str] | None = None,
    penalties: dict | None = None,
) -> list[dict]:
    """
    Score jobs by overlap between the user's roles/skills/tools/category and each
    job's title + description. Pure text — no embeddings, no AI. Used when vector
    matching isn't available. Returns the top `limit` jobs with a match_score,
    preferring ones the user hasn't seen before (see _prioritize_fresh).

    Category relevance is enforced BEFORE any scoring or backfill — a job
    must belong to the user's profession (via _category_relevant) to be a
    candidate at all. This is what stops a generic skill term ("figma",
    "javascript") from loosely matching a job in a completely different
    field: an honestly small (or empty) digest beats a padded wrong-
    category one.
    """
    seen = seen or {}
    penalties = penalties or {"exclude_companies": set(), "demote_title_tokens": set()}
    user_category = (user.get("job_category") or "").strip()
    candidates = [j for j in jobs if _category_relevant(j, user_category, _category_terms(user))]
    # Excluded companies are dropped before scoring (a hard "never again");
    # wrong-role title demotion must wait until AFTER scoring — it works by
    # multiplying match_score, which doesn't exist yet on raw candidates.
    if penalties["exclude_companies"]:
        candidates = [
            j for j in candidates
            if str(j.get("company") or "").strip().lower() not in penalties["exclude_companies"]
        ]

    terms = _user_terms(user)
    if not terms:
        # Nothing to score on — still only from in-category candidates.
        return _prioritize_fresh([{**job, "match_score": 0.3} for job in candidates], seen, limit)

    scored: list[dict] = []
    for job in candidates:
        title_words = _tokenize(job.get("title", ""))
        body_words = title_words | _tokenize(job.get("description", ""))
        # Whole-word matching (avoids "design" matching "designer", etc.).
        hits = sum(1 for t in terms if t in body_words)
        if hits:
            title_hits = sum(1 for t in terms if t in title_words)
            raw = (hits + title_hits * 2) / (len(terms) + 2)
            score = round(min(0.98, 0.5 + raw), 4)
            if score >= MIN_KEYWORD_SCORE:
                scored.append({**job, "match_score": score})

    # Wrong-role demotion (halves match_score), then re-apply the floor —
    # a demoted lookalike dropping below MIN_KEYWORD_SCORE is the intended
    # outcome, not a survivor with a small number.
    scored = _apply_relevance_penalties(scored, penalties)
    scored = [j for j in scored if j["match_score"] >= MIN_KEYWORD_SCORE]

    scored.sort(key=lambda j: j["match_score"], reverse=True)
    if scored:
        return _prioritize_fresh(scored, seen, limit)
    # No genuine keyword overlap even within category — still don't reach
    # outside it for filler.
    return _prioritize_fresh([{**job, "match_score": 0.3} for job in candidates], seen, limit)


async def store_matches(user_id: str, matched_jobs: list[dict]) -> int:
    """
    Store matched jobs in the user_jobs table.
    Only stores today's digest — skips if already processed.
    """
    supabase = get_supabase()
    today = date.today().isoformat()

    rows = []
    fresh_job_ids: set[str] = set()
    for rank, job in enumerate(matched_jobs, start=1):
        # The replaced match_jobs SQL function (migration_v2_1.sql) returns
        # percentage scores (0–100) while everything else here uses 0–1 —
        # normalize so stored scores are always 0–1 regardless of which
        # version of the function the database has.
        score = job.get("match_score", 0.0) or 0.0
        if score > 1:
            score = score / 100.0
        fresh_job_ids.add(job["id"])
        rows.append({
            "user_id": user_id,
            "job_id": job["id"],
            "match_score": round(min(score, 1.0), 4),
            "rank": rank,
            "digest_date": today,
            "status": "matched",
        })

    # A same-day re-run (e.g. after fixing a matching bug like the
    # cross-category one) computes a fresh ranking, but the upsert below
    # uses ignore_duplicates=True — it only ADDS rows, it never removes
    # ones from the previous ranking that fell out. Without this, a stale
    # wrong match from an earlier run today would sit in the digest forever
    # alongside the new correct ones, and re-running the pipeline could
    # never actually fix it. Safe to clean up: only rows still in the raw
    # 'matched' state (no resume/PDF/feedback/email progress) are removed —
    # anything a user has already seen or the pipeline has already worked
    # on is left untouched.
    #
    # This deliberately runs even when the fresh ranking is EMPTY: that is
    # exactly the case where every stored match from an earlier buggy run
    # was wrong (nothing in the pool survives the corrected filter), so
    # skipping cleanup here would leave the user permanently stuck with
    # only the bad rows.
    try:
        stale_resp = (
            supabase.table("user_jobs")
            .select("id, job_id")
            .eq("user_id", user_id)
            .eq("digest_date", today)
            .eq("status", "matched")
            .execute()
        )
        stale_ids = [r["id"] for r in (stale_resp.data or []) if r.get("job_id") not in fresh_job_ids]
        if stale_ids:
            supabase.table("user_jobs").delete().in_("id", stale_ids).execute()
            logger.info(f"   Removed {len(stale_ids)} stale unprogressed match(es) for {user_id} (today, no longer in the fresh ranking)")
    except Exception as e:
        logger.warning(f"   Couldn't clean stale matches for {user_id} ({e}) — continuing anyway.")

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
