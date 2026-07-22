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
from core.skill_maps import JOB_CATEGORIES, GENERIC_ROLE_WORDS
from database.supabase_client import get_supabase
# Safe import direction: jobs.fetchers never imports core.matcher.
from jobs.fetchers import experience_months_from_text

logger = logging.getLogger(__name__)
settings = get_settings()


# Words like "designer"/"developer"/"engineer"/"manager"/"product" appear in
# MORE THAN ONE job_category's real role vocabulary (ui_ux_designer's
# "Product Designer" AND product_manager's "Product Manager" both contain
# "product"; ui_ux_designer AND graphic_designer both contain "designer").
# A single shared word is not evidence a job is in the RIGHT one of those
# professions — without this exclusion, an untagged Product Designer job's
# title passes a developer's category gate on "product" alone (2026-07
# production incident: Kevin's profile). GENERIC_ROLE_WORDS is imported
# from core/skill_maps.py rather than computed here so this exclusion and
# jobs/fetchers.py's fetch-time title filter share ONE mechanically-derived
# set — the previous version of this fix lived only in fetchers.py's own
# hand-maintained word list and was never ported here, which is exactly how
# "product" caused the same leak twice. Only affects the untagged-job
# text-fallback path in _category_relevant; jobs with a real search_category
# tag are matched exactly, unaffected.
_GENERIC_ROLE_NOUNS = GENERIC_ROLE_WORDS

# Words so common in ANY job's text that they carry zero category signal —
# "it" (from e.g. a "Technical IT Engineer" target role) is literally the
# English pronoun in every description, and "technical"/seniority words
# appear in most. These leaked graphic-design jobs to a Python/AI user in
# production: the 2-term description fallback cleared on "it" + "data".
# Gating terms only — scoring (_user_terms) is unaffected.
_GATE_STOPWORDS = {"it", "technical", "senior", "junior", "lead"}


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


def _user_categories(user: dict) -> set[str]:
    """Primary job_category plus any secondary_categories ("also open to")
    the user chose. All of them count as the user's profession for the
    relevance gate — a fullstack dev open to backend roles should see
    backend-tagged jobs, and only these categories, not everything.

    When job_category is EMPTY, fall back to one inferred from target_roles
    (skill_maps.resolve_user_category) — a user with real HR roles but a
    blank category must still gate to HR, not to nothing (which passes no
    jobs) nor to the ui_ux_designer default."""
    from core.skill_maps import resolve_user_category
    primary = resolve_user_category(user) or ""
    cats = {primary.strip()}
    cats |= {(c or "").strip() for c in (user.get("secondary_categories") or [])}
    return {c for c in cats if c}


def _category_terms(user: dict) -> set[str]:
    """Narrower term set (categories + target roles ONLY, no skills/tools)
    used for category RELEVANCE gating — deliberately excludes skills/
    tools because those are too generic and are exactly why a Fullstack
    Developer's "javascript"/"api" skills could loosely match a UI/UX
    Designer job description under the broader _user_terms set."""
    terms: set[str] = set()
    for category in _user_categories(user):
        terms |= {w for w in _tokenize(category.replace("_", " ")) if len(w) >= 2}
    for role in (user.get("target_roles") or []):
        terms |= {w for w in _tokenize(role) if len(w) >= 2}
    return terms


def _category_relevant(job: dict, user_categories: set[str], category_terms: set[str]) -> bool:
    """
    True when `job` belongs to one of the user's professions (primary
    job_category + secondary_categories). Prefers the exact
    search_category tag stamped at fetch time (jobs/fetchers.py); jobs
    fetched before that column existed, or returned by the vector-search
    RPC (which doesn't carry the tag), fall back to a text check — at
    least one category/target-role term in the title, or two in the
    description — rather than being silently excluded or blindly included.
    """
    tag = job.get("search_category")
    if tag:
        return tag in user_categories
    if not category_terms:
        return True  # nothing to check against — don't blanket-exclude
    # Generic multi-category nouns ("designer", "developer", ...) and
    # no-signal stopwords ("it", "technical", ...) can't clear either gate
    # alone — see _GENERIC_ROLE_NOUNS / _GATE_STOPWORDS above.
    specific_terms = category_terms - _GENERIC_ROLE_NOUNS - _GATE_STOPWORDS
    title_words = _tokenize(job.get("title", ""))
    desc_words = _tokenize(job.get("description", ""))
    if not specific_terms:
        # Every gating term was generic (e.g. "data engineer" — both words
        # multi-category, or a category like ui_ux_designer whose own
        # label "UI/UX Designer" tokenizes entirely into words that are
        # ALSO real target_roles of other categories). No single word here
        # is safe alone — the weak full-set 2-co-occurrence check (same
        # bar as the description fallback below) beats blanket-passing.
        return len((category_terms - _GATE_STOPWORDS) & desc_words) >= 2
    if specific_terms & title_words:
        return True
    # Description fallback: two co-occurring SPECIFIC terms. (This used to
    # allow the full term set including generic nouns — which is exactly
    # how a graphic-design description passed for a Python/AI user on
    # "it" + "data".)
    return len(specific_terms & desc_words) >= 2


# ── Experience-level gate (TICKET-031) ────────────────────────────────────────
# Two vocabularies live side by side: users pick fresher/junior/mid/senior
# at signup (ProfileEditor.tsx), while jobs carry entry/mid/senior/lead
# (JSearch title inference). Both map onto the same band scale here.
#
# Top of each user band in months — a job requiring more than this plus
# the tolerance is hard-excluded. None = no upper cap (senior users are
# never priced out upward).
_USER_BAND_TOP_MONTHS: dict[str, int | None] = {
    "fresher": 12, "entry": 12,
    "junior": 36,
    "mid": 60,
    "senior": None, "lead": None,
}
# 2026-07: was 12, which let a "2-5 years" job (24-month floor) pass for a
# fresher (top=12) — a floor-only check treats "2-5 years" the same as a
# flat "2 years" ask, but a job seeker reading "2-5 years required" does
# not perceive themselves as qualified at 0-1 years. Zero tolerance means
# the ceiling is exactly each band's own top: a fresher's "1-2 years" job
# (floor=12=their own top) still passes with NO tolerance needed; nothing
# requiring more than the user's stated band does. Matches this section's
# original intent ("stretch to '1-2 years'; never to '5+'") exactly,
# instead of contradicting it.
_EXPERIENCE_TOLERANCE_MONTHS = 0

# Band indices for the coarse fallback when a job has no months data —
# only the title-inferred seniority_level. User side:
_USER_BAND_INDEX = {"fresher": 0, "entry": 0, "junior": 0, "mid": 1, "senior": 2, "lead": 2}
# Job side ("lead" sits above "senior" so mid users don't get lead roles):
_JOB_BAND_INDEX = {"entry": 0, "junior": 0, "fresher": 0, "mid": 1, "senior": 2, "lead": 3}

# Senior users seeing entry-level jobs: allowed (their call) but nudged
# down so their digest leads with band-appropriate roles.
_EXPERIENCE_DOWNLEVEL_PENALTY = 0.9


def _job_required_months(job: dict) -> int | None:
    """
    Required experience for a job, in months. The stored column when
    present; otherwise parsed from the description ON THE FLY — jobs
    fetched before the required_experience_months column shipped are all
    NULL there, yet many state the requirement in plain text ("7+ years of
    experience"), and "unknown passes the gate" must not apply to those.
    The parse result is written back onto the dict so repeat callers
    (gate, penalty, breakdown) don't re-run the regex.
    """
    months = job.get("required_experience_months")
    if isinstance(months, (int, float)) and months > 0:
        return int(months)
    description = job.get("description")
    if description:
        parsed = experience_months_from_text(description)
        job["required_experience_months"] = parsed  # cache (None is fine)
        return parsed
    return None


def _job_band_index(job: dict) -> int | None:
    """Coarse band for a job: months when known, else title-inferred
    seniority_level, else None (unknown)."""
    months = _job_required_months(job)
    if months:
        return 0 if months < 36 else (1 if months < 60 else 2)
    return _JOB_BAND_INDEX.get((job.get("seniority_level") or "").strip().lower())


def _experience_ok(job: dict, user_level: str, hide_unknown: bool = False) -> bool:
    """
    Hard gate: False only when the job demonstrably asks for more
    experience than the user's band can stretch to. Unknown data (no
    months, no seniority) passes by default — unknown is not disqualified —
    and users with no/unrecognized level are never filtered.

    hide_unknown (the user's opt-in "only jobs I clearly qualify for"
    toggle): when True, a job with NO readable experience signal is also
    excluded. Off by default so the pool stays broad for everyone who
    hasn't asked to narrow it.
    """
    if hide_unknown and _job_band_index(job) is None:
        return False
    level = (user_level or "").strip().lower()
    if level not in _USER_BAND_TOP_MONTHS:
        return True
    top = _USER_BAND_TOP_MONTHS[level]
    if top is None:
        return True  # senior/lead users: no upward exclusion possible
    months = _job_required_months(job)
    if months:
        return months <= top + _EXPERIENCE_TOLERANCE_MONTHS
    job_idx = _JOB_BAND_INDEX.get((job.get("seniority_level") or "").strip().lower())
    if job_idx is None:
        return True
    return job_idx - _USER_BAND_INDEX[level] < 2


# A fresher/entry/junior user's job_idx is 0 — _apply_experience_penalty's
# down-level branch never fires for them (nothing is below the bottom
# band), so without this they had no defense against jobs with NO
# experience signal at all outranking jobs we're actually confident fit.
# Milder than _EXPERIENCE_DOWNLEVEL_PENALTY on purpose: a downlevel job is
# CONFIRMED too easy for the user; an unknown-experience job might be
# perfectly fine — matcher.py's documented policy is "unknown is not
# disqualified," so this only reorders, it never excludes.
_UNKNOWN_EXPERIENCE_PENALTY = 0.85


def _apply_experience_penalty(jobs: list[dict], user_level: str) -> list[dict]:
    """
    Post-scoring nudge, two directions:
    - A job 2+ bands BELOW the user gets its score multiplied down (never
      dropped — a senior may genuinely want it).
    - For fresher/entry/junior users specifically, a job with NO
      experience signal at all (neither parsed required_experience_months
      nor an inferred seniority_level — see jobs/fetchers.py's
      infer_seniority_level) gets the milder _UNKNOWN_EXPERIENCE_PENALTY.
      This is what a fresher's dashboard actually shows more of: jobs
      confidently within their band, ranked above jobs we simply have no
      data on, rather than the two being indistinguishable in the list.
    """
    level = (user_level or "").strip().lower()
    user_idx = _USER_BAND_INDEX.get(level)
    if user_idx is None:  # unrecognized level — never filtered or penalized
        return jobs
    for j in jobs:
        job_idx = _job_band_index(j)
        if job_idx is not None and user_idx - min(job_idx, 2) >= 2:
            j["match_score"] = round((j.get("match_score") or 0) * _EXPERIENCE_DOWNLEVEL_PENALTY, 4)
        elif user_idx == 0 and job_idx is None:
            j["match_score"] = round((j.get("match_score") or 0) * _UNKNOWN_EXPERIENCE_PENALTY, 4)
    return jobs


def _experience_fit_label(job: dict, user_level: str) -> str | None:
    """'match' / 'stretch' / 'below' for the honest breakdown — None when
    the job has no experience data or the user level is unknown (the
    breakdown only ever carries actually-computed facts)."""
    user_idx = _USER_BAND_INDEX.get((user_level or "").strip().lower())
    job_idx = _job_band_index(job)
    if user_idx is None or job_idx is None:
        return None
    job_idx = min(job_idx, 2)
    if job_idx == user_idx:
        return "match"
    return "stretch" if job_idx > user_idx else "below"


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
    Also Open To: {', '.join(c.replace('_', ' ') for c in (user.get('secondary_categories') or []))}
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


# Statuses that mean the USER acted on a match — purge never touches these.
_PURGE_PROTECTED_STATUSES = {"applied", "interviewing", "offered"}


async def purge_miscategorized_matches(
    supabase, user_id: str, user_categories: set[str], category_terms: set[str]
) -> int:
    """
    Self-healing cleanup for HISTORICAL category leaks (2026-07: Kevin's
    developer dashboard kept showing Product Designer jobs even after the
    gate was fixed). The gate only filters NEW candidates; the dashboard
    shows every stored user_jobs row regardless of date, and
    store_matches' stale-row cleanup only removes TODAY's still-'matched'
    rows — so a leaked row that progressed (resume generated, pdf_failed,
    emailed) would otherwise sit on the dashboard forever.

    Re-runs the exact same _category_relevant gate over ALL of the user's
    stored matches and deletes the ones that no longer pass, EXCEPT rows
    the user has acted on (applied/interviewing/offered, an applied_at or
    application_status value, or any feedback — feedback rows feed the
    personalization penalties and must survive).

    Best-effort: any failure logs and returns 0 — cleanup must never block
    matching (same contract as _load_relevance_penalties). Returns the
    number of rows removed.
    """
    try:
        resp = (
            supabase.table("user_jobs")
            .select(
                "id, status, applied_at, application_status, feedback, job_feedback, "
                "jobs(title, description, search_category, source)"
            )
            .eq("user_id", user_id)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        logger.info(f"   Skipping mis-categorization purge ({e}) — matching proceeds unaffected.")
        return 0

    stale_ids = []
    for row in rows:
        if (row.get("status") or "") in _PURGE_PROTECTED_STATUSES:
            continue
        if row.get("applied_at") or row.get("application_status"):
            continue
        if row.get("feedback") or row.get("job_feedback"):
            continue
        job = row.get("jobs") or {}
        if job.get("source") == "user_submitted":
            # The user explicitly added this job themselves (AI Application
            # Review intake) — it never went through category-tagged
            # fetching, and "you chose it" outranks any gate's opinion.
            continue
        if not job.get("title"):
            continue  # can't judge without the job — leave it alone
        if not _category_relevant(job, user_categories, category_terms):
            stale_ids.append(row["id"])

    if not stale_ids:
        return 0
    try:
        supabase.table("user_jobs").delete().in_("id", stale_ids).execute()
        logger.info(f"   🧹 Removed {len(stale_ids)} mis-categorized historical match(es) for user {user_id}")
        return len(stale_ids)
    except Exception as e:
        logger.warning(f"   Mis-categorization purge delete failed ({e}) — continuing anyway.")
        return 0


async def purge_overqualified_matches(supabase, user_id: str, experience_level: str) -> int:
    """
    Sibling of purge_miscategorized_matches for the OTHER long-running
    leak: stored matches whose job we NOW know asks for more experience
    than the user's band. Adzuna's API truncates descriptions, so many
    jobs match as "unknown experience" (which passes the gate by policy)
    and only LATER get their real requirement filled in by the classify/
    page-fetch step — but the match row created before that stayed on the
    dashboard indefinitely. Re-runs the exact same _experience_ok gate
    over all stored matches against today's job data; same protections as
    the category purge (user-acted rows and user-submitted jobs survive).

    Best-effort: any failure logs and returns 0 — cleanup must never
    block matching.
    """
    level = (experience_level or "").strip().lower()
    if _USER_BAND_TOP_MONTHS.get(level) is None:
        # senior/lead (or unrecognized level): no upward exclusion exists,
        # so there's nothing to heal.
        return 0
    try:
        resp = (
            supabase.table("user_jobs")
            .select(
                "id, status, applied_at, application_status, feedback, job_feedback, "
                "jobs(title, description, seniority_level, required_experience_months, source)"
            )
            .eq("user_id", user_id)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        logger.info(f"   Skipping over-qualification purge ({e}) — matching proceeds unaffected.")
        return 0

    stale_ids = []
    for row in rows:
        if (row.get("status") or "") in _PURGE_PROTECTED_STATUSES:
            continue
        if row.get("applied_at") or row.get("application_status"):
            continue
        if row.get("feedback") or row.get("job_feedback"):
            continue
        job = row.get("jobs") or {}
        if job.get("source") == "user_submitted":
            continue  # the user chose it — never auto-remove
        if not job.get("title"):
            continue
        if not _experience_ok(job, level):
            stale_ids.append(row["id"])

    if not stale_ids:
        return 0
    try:
        supabase.table("user_jobs").delete().in_("id", stale_ids).execute()
        logger.info(f"   🧹 Removed {len(stale_ids)} over-qualified historical match(es) for user {user_id}")
        return len(stale_ids)
    except Exception as e:
        logger.warning(f"   Over-qualification purge delete failed ({e}) — continuing anyway.")
        return 0


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
    supabase = get_supabase()

    # 1. Get user profile
    user_resp = supabase.table("users").select("*").eq("id", user_id).single().execute()
    if not user_resp.data:
        logger.error(f"❌ User {user_id} not found")
        return []

    user = user_resp.data
    # Caller's explicit limit wins; otherwise the per-user admin override
    # (T-023, select("*") already includes it when the column exists);
    # otherwise the global MAX_JOBS_PER_USER default.
    if limit is None:
        limit = user.get("job_count_override") or settings.max_jobs_per_user
    logger.info(f"🎯 Matching jobs for user: {user.get('name', user_id)}")

    # Self-heal past leaks BEFORE computing the fresh ranking, so this
    # run's freshness/dedup logic doesn't count soon-to-be-deleted rows as
    # "seen" history worth avoiding: category leaks, and matches whose job
    # we NOW know asks for more experience than this user has.
    await purge_miscategorized_matches(supabase, user_id, _user_categories(user), _category_terms(user))
    await purge_overqualified_matches(supabase, user_id, user.get("experience_level") or "")

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
            # include search_category or the experience columns, so a high
            # cosine-similarity score alone can still be the wrong
            # profession entirely — or a 5-year role shown to a fresher
            # (embeddings can't compare numbers). Batch-fetch those
            # columns for these candidates and gate on them.
            user_categories = _user_categories(user)
            category_terms = _category_terms(user)
            user_level = user.get("experience_level") or ""
            hide_unknown = bool(user.get("hide_unknown_experience"))
            job_ids = [j["id"] for j in jobs if j.get("id")]
            meta_by_id: dict[str, dict] | None = {}
            if job_ids:
                try:
                    meta_resp = (
                        supabase.table("jobs")
                        .select("id, search_category, seniority_level, required_experience_months")
                        .in_("id", job_ids)
                        .execute()
                    )
                    meta_by_id = {row["id"]: row for row in (meta_resp.data or [])}
                except Exception as e:
                    # required_experience_months is the newest column — an
                    # unmigrated DB shouldn't lose category filtering too.
                    try:
                        cat_resp = supabase.table("jobs").select("id, search_category").in_("id", job_ids).execute()
                        meta_by_id = {row["id"]: row for row in (cat_resp.data or [])}
                    except Exception:
                        logger.warning(f"   Couldn't load candidate metadata ({e}) — skipping category/experience filters this run.")
                        meta_by_id = None  # signals "don't filter" below

            if meta_by_id is not None:
                for j in jobs:
                    meta = meta_by_id.get(j.get("id")) or {}
                    j["search_category"] = meta.get("search_category")
                    j["seniority_level"] = meta.get("seniority_level")
                    j["required_experience_months"] = meta.get("required_experience_months")
                relevant = [
                    j for j in jobs
                    if _category_relevant(j, user_categories, category_terms) and _experience_ok(j, user_level, hide_unknown)
                ]
                no_exp_data = sum(1 for j in relevant if _job_band_index(j) is None)
                if no_exp_data:
                    logger.info(f"   {no_exp_data}/{len(relevant)} vector candidates have no experience data (passed unfiltered)")
            else:
                # Metadata load failed — degrade to the tag-less TEXT gate,
                # not to no gate at all (a transient DB hiccup must never
                # mean "show every profession to everyone" for that run).
                relevant = [j for j in jobs if _category_relevant(j, user_categories, category_terms)]

            relevant = _apply_relevance_penalties(relevant, penalties)
            relevant = _apply_experience_penalty(relevant, user_level)
            relevant.sort(key=lambda j: j.get("match_score") or 0, reverse=True)

            if relevant:
                fresh_jobs = _prioritize_fresh(relevant, seen, limit)
                for j in fresh_jobs:
                    j["match_breakdown"] = _build_breakdown(user, j, source="vector")
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


def _build_breakdown(user: dict, job: dict, source: str) -> dict:
    """
    "Why this matched" — ONLY facts the matcher actually computed
    (docs/PRODUCT_STRATEGY_BETA.md: no decorative numbers, ever). Term
    overlap is recomputed from the same _user_terms set the keyword scorer
    uses; the vector path additionally carries its real similarity score.
    Description text may be absent on RPC rows — then only title terms
    show, which is still honest.
    """
    terms = _user_terms(user)
    title_words = _tokenize(job.get("title", ""))
    body_words = title_words | _tokenize(job.get("description", ""))
    matched = sorted(t for t in terms if t in body_words)[:12]
    title_matched = sorted(t for t in terms if t in title_words)[:8]
    breakdown: dict = {
        "source": source,
        "matched_terms": matched,
        "title_terms": title_matched,
    }
    if source == "vector":
        score = job.get("match_score") or 0
        breakdown["similarity"] = round(score / 100.0 if score > 1 else score, 4)
    # Only when the job actually carries experience data AND the user has
    # a recognized level — never an invented value.
    fit = _experience_fit_label(job, user.get("experience_level") or "")
    if fit:
        breakdown["experience_fit"] = fit
    return breakdown


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
    user_categories = _user_categories(user)
    user_level = user.get("experience_level") or ""
    category_terms = _category_terms(user)
    hide_unknown = bool(user.get("hide_unknown_experience"))
    candidates = [
        j for j in jobs
        if _category_relevant(j, user_categories, category_terms) and _experience_ok(j, user_level, hide_unknown)
    ]
    no_exp_data = sum(1 for j in candidates if _job_band_index(j) is None)
    if no_exp_data:
        logger.info(f"   {no_exp_data}/{len(candidates)} keyword candidates have no experience data (passed unfiltered)")
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
    scored = _apply_experience_penalty(scored, user_level)
    scored = [j for j in scored if j["match_score"] >= MIN_KEYWORD_SCORE]

    scored.sort(key=lambda j: j["match_score"], reverse=True)
    if scored:
        result = _prioritize_fresh(scored, seen, limit)
        for j in result:
            j["match_breakdown"] = _build_breakdown(user, j, source="keyword")
        return result
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
        row = {
            "user_id": user_id,
            "job_id": job["id"],
            "match_score": round(min(score, 1.0), 4),
            "rank": rank,
            "digest_date": today,
            "status": "matched",
        }
        if job.get("match_breakdown"):
            row["match_breakdown"] = job["match_breakdown"]
        rows.append(row)

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
        # match_breakdown is a newer column — an un-run migration must cost
        # the "why this matched" detail, never the matches themselves (same
        # pattern as store_jobs' search_category fallback).
        if any("match_breakdown" in r for r in rows):
            logger.warning(f"⚠️  Upsert with match_breakdown failed ({e}) — retrying without it.")
            stripped = [{k: v for k, v in r.items() if k != "match_breakdown"} for r in rows]
            resp = (
                supabase.table("user_jobs")
                .upsert(stripped, on_conflict="user_id,job_id,digest_date", ignore_duplicates=True)
                .execute()
            )
            count = len(resp.data) if resp.data else 0
            logger.info(f"✅ Stored {count} job matches for user {user_id} (without match_breakdown)")
            return count
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
