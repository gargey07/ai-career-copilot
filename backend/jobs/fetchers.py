"""
Job Fetchers — Adzuna + JSearch (LinkedIn via RapidAPI)
────────────────────────────────────────────────────────
Fetches jobs from external APIs, normalizes them into a
consistent schema, and stores them in the central jobs table.

Run standalone to test:
    python fetchers/run_fetch.py
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings
from core.locations import ADZUNA_COUNTRIES, resolve_fetch_location
from core.skill_maps import GENERIC_ROLE_WORDS
from core.usage_guard import check_budget
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Required-experience extraction ────────────────────────────────────────────
# "N years"/"N+ years"/"N-M years" mentions. The surrounding-context check
# below is what makes this safe to run on whole descriptions: "2+ years of
# experience" counts, "founded 25 years ago" does not.
_YEARS_RE = re.compile(r"(\d{1,2})\s*(?:\+|\s*(?:-|–|to)\s*\d{1,2})?\s*(?:years?|yrs?)\b", re.IGNORECASE)

# 2026-07: a fresher/entry user (0-1 yrs) kept seeing plainly-titled "7+
# years" jobs. Traced to this context check being too narrow — real
# requirement phrasing very often doesn't put the literal word
# "experience"/"exp" near the number ("5+ years in a similar role",
# "minimum 5 years", "3-5 years building production systems"), so it
# silently parsed to None and fell through to the (much weaker) seniority-
# band fallback. Kept as a POSITIVE-anchor allowlist rather than switching
# to a blacklist of company-age words ("founded 25 years ago") — an
# allowlist can only miss real requirements (safe direction), a blacklist
# could newly accept a company-history mention that happens not to use any
# of those specific words (unsafe direction: a false requirement gate).
_EXPERIENCE_CONTEXT_RE = re.compile(
    r"\bexp(?:erience|\b|\.)"
    r"|\byears?\s+(?:in|of|working|building)\b"
    r"|\byoe\b"
    r"|\b(?:minimum|min\.?|at\s+least)\b"
    r"|\bbackground\s+in\b"
    r"|\btrack\s+record\b"
    r"|\b(?:proven|professional|relevant|industry|hands-on|practical|prior)\b"
    r"|\brequir(?:ed|ement)\b",
    re.IGNORECASE,
)
# Wide enough to span a "Requirements:" bullet where the anchor word sits
# in a heading or an adjacent line, not literally next to the number.
_EXPERIENCE_CONTEXT_WINDOW = 100  # chars each side of a "N years" hit
_MAX_PLAUSIBLE_YEARS = 40

# Spelled-out numbers ("at least three years") — same anchor-context rule
# applies, just matched as words instead of digits.
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_WORD_YEARS_RE = re.compile(
    r"\b(" + "|".join(_WORD_NUMBERS) + r")\s*(?:years?|yrs?)\b", re.IGNORECASE
)


def experience_months_from_text(text: str) -> Optional[int]:
    """
    Minimum required experience (in months) stated in a job description,
    or None when nothing credible is found. Takes the LOWEST qualifying
    number — "2-4 years" and "2+ years" both mean a 2-year floor. Only
    counts a "N years" mention with a requirement-shaped word nearby (see
    _EXPERIENCE_CONTEXT_RE), so marketing copy ("serving clients for 15
    years") doesn't poison it.
    """
    if not text:
        return None
    years_found: list[int] = []

    def _context_ok(start_idx: int, end_idx: int) -> bool:
        start = max(0, start_idx - _EXPERIENCE_CONTEXT_WINDOW)
        end = min(len(text), end_idx + _EXPERIENCE_CONTEXT_WINDOW)
        return bool(_EXPERIENCE_CONTEXT_RE.search(text[start:end]))

    for m in _YEARS_RE.finditer(text):
        years = int(m.group(1))
        if years == 0 or years > _MAX_PLAUSIBLE_YEARS:
            continue
        if _context_ok(m.start(), m.end()):
            years_found.append(years)

    for m in _WORD_YEARS_RE.finditer(text):
        years = _WORD_NUMBERS[m.group(1).lower()]
        if _context_ok(m.start(), m.end()):
            years_found.append(years)

    return min(years_found) * 12 if years_found else None


# ── Seniority inference from title ────────────────────────────────────────────
_SENIOR_TITLE_RE = re.compile(r"\b(senior|sr\.?|staff|principal|architect|iii|iv)\b", re.IGNORECASE)
_LEAD_TITLE_RE = re.compile(r"\blead\b", re.IGNORECASE)
_ENTRY_TITLE_RE = re.compile(r"\b(junior|jr\.?|intern|fresher|entry[\s-]?level|graduate|trainee|i)\b", re.IGNORECASE)


def infer_seniority_level(title: str) -> Optional[str]:
    """
    Best-effort seniority band from a job TITLE alone. Only JSearch's API
    provides a structured seniority field — every other source needs this
    fallback, and JSearch itself falls back to it too when its own title
    doesn't say senior/lead/entry.

    Returns None — never a guessed default — when the title gives no
    confident signal. An earlier version of this defaulted every
    unmatched title to "mid", and that fake label was WORSE than no label
    at all: matcher.py's band-distance check treats "mid" as close enough
    to pass a fresher/entry user straight through, so a plainly-titled
    "Software Engineer" requiring 7 years (title says nothing about
    seniority) was being waved through on a guess dressed up as data.
    matcher.py already has a deliberate, documented "unknown passes"
    policy for genuinely missing data — a wrong "mid" bypassed even that.
    """
    if not title:
        return None
    t = title.lower()
    if _SENIOR_TITLE_RE.search(t):
        return "senior"
    if _LEAD_TITLE_RE.search(t):
        return "lead"
    if _ENTRY_TITLE_RE.search(t):
        return "entry"
    return None


# ── Application-page text (experience enrichment) ─────────────────────────────
# Many Adzuna listings state the experience requirement ONLY on the
# company's own ATS page behind the apply link ("Required Experience:
# 2 - 5 Years" on e.g. PeopleStrong), never in the truncated description
# Adzuna's API returns — so neither the description regex nor the AI
# classifier (which also only saw the description) could ever find it.
# These helpers fetch that page's visible text so the SAME parsers get a
# shot at the place the requirement actually lives.

_PAGE_FETCH_TIMEOUT_SECONDS = 8.0
_PAGE_FETCH_MAX_BYTES = 500_000
# A real browser-ish UA — several ATS providers hard-block default
# python-httpx UAs with a 403 while serving the identical page otherwise.
_PAGE_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AICareerCopilot/1.0; +jobs-metadata)"}


def _extract_page_text(html: str) -> str:
    """Visible text from an HTML page — scripts/styles dropped, whitespace
    collapsed. Best-effort: any parse failure returns ""."""
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    except Exception:
        return ""


async def fetch_job_page_text(url: str) -> str:
    """
    Visible text of a job's application page, or "" on ANY failure —
    bad/synthetic URL (JSearch rows without an apply link store
    "jsearch_<id>"), timeout, non-HTML response, JS-only page that ships
    an empty shell. Callers must treat "" as "page told us nothing",
    never as an error: this is enrichment, and plenty of ATS pages are
    client-rendered and legitimately yield nothing over plain HTTP.
    """
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return ""
    try:
        async with httpx.AsyncClient(
            timeout=_PAGE_FETCH_TIMEOUT_SECONDS, follow_redirects=True, headers=_PAGE_FETCH_HEADERS
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return ""
            content_type = resp.headers.get("content-type", "")
            if "html" not in content_type and "text" not in content_type:
                return ""
            return _extract_page_text(resp.text[:_PAGE_FETCH_MAX_BYTES])
    except Exception:
        return ""


# ── Normalized Job Schema ─────────────────────────────────────────────────────
def normalize_job(
    source: str,
    external_id: str,
    title: str,
    company: str,
    location: str,
    description: str,
    source_url: str,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    employment_type: Optional[str] = None,
    seniority_level: Optional[str] = None,
    is_remote: bool = False,
    posted_at: Optional[str] = None,
    required_experience_months: Optional[int] = None,
) -> dict:
    """Normalize any job from any source into a common schema.

    required_experience_months: structured value when the source provides
    one (only JSearch does); otherwise parsed from the description here so
    every source gets the same treatment. None means "unknown" — the
    matcher treats that as unfilterable, never as "no requirement".

    seniority_level: same idea — inferred from the title here (previously
    only JSearch's fetch loop computed this, leaving Adzuna/Remotive/
    Greenhouse/Jobicy jobs with no signal at all for the experience gate's
    fallback path)."""
    if required_experience_months is None:
        required_experience_months = experience_months_from_text(description or "")
    if seniority_level is None:
        seniority_level = infer_seniority_level(title)
    return {
        "source": source,
        "external_id": str(external_id),
        "source_url": source_url,
        "title": title,
        "company": company or "Unknown Company",
        "location": location or "Not specified",
        "description": description or "",
        "salary_min": salary_min,
        "salary_max": salary_max,
        "employment_type": employment_type,
        "seniority_level": seniority_level,
        "is_remote": is_remote,
        "required_experience_months": required_experience_months,
        "posted_at": posted_at,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Location resolution ───────────────────────────────────────────────────────
# ADZUNA_COUNTRIES and resolve_fetch_location() now live in core/locations.py
# (shared with the /api/suggestions/locations autosuggest endpoint) —
# imported above.


# ── Query matching (profession-agnostic) ──────────────────────────────────────
_STOPWORDS = {"the", "and", "for", "with", "job", "jobs", "role", "roles", "senior", "junior"}

# Qualifier words that prefix MANY unrelated professions — "product" alone
# can't tell "Product Manager" from "Product Designer" apart. GENERIC_ROLE_WORDS
# (core/skill_maps.py) is mechanically derived from every category's real role
# vocabulary and shared with core/matcher.py's category gate — importing it
# here (not matcher.py itself, which WOULD be circular since matcher.py
# imports from this module) means a newly-ambiguous word only needs to exist
# in the category data to be excluded everywhere, instead of being hand-added
# to two separate word lists that can silently drift apart (exactly how
# "product" got fixed here once but not in matcher.py, causing the same leak
# to resurface on the dashboard). A few pure seniority/scope qualifiers that
# don't come from any category's target_roles at all are unioned in on top.
_QUALIFIER_WORDS = GENERIC_ROLE_WORDS | {
    "digital", "content", "technical", "creative",
    "associate", "principal", "staff", "chief", "global", "regional",
}


def _query_terms(query: str) -> list[str]:
    """Meaningful lowercase words from a search query (drops noise/stopwords)."""
    return [w for w in re.findall(r"[a-z0-9+#]+", (query or "").lower()) if len(w) >= 2 and w not in _STOPWORDS]


def _title_matches(title: str, query: str) -> bool:
    """
    True if the job title is relevant to the query. Empty query = accept all.
    Replaces the old hardcoded design-only keyword filters so fetchers work for
    any profession (backend, PM, marketing, etc.).

    Word-boundary matching (tokenized set membership), NOT substring
    containment — a naive `"ai" in title.lower()` matches "email"/"retail"/
    "detail", and `"product" in title.lower()` matched "Product Designer"
    for a "Product Manager" query, showing a developer's profile a UX
    design job requiring "3+ years of UX/UI design experience" (a live
    production bug). Qualifier words are excluded from what counts as a
    match — "Product Manager" needs "manager" specifically, not just any
    shared prefix word.

    Many real queries are TWO qualifier words together ("Product Manager",
    "UI UX Designer", "Data Engineer" — every word individually ambiguous
    across professions, e.g. "manager" alone spans Product/Project/Account/
    HR Manager). When that leaves zero specific terms, falling back to
    "match ANY of the original words" would accept a title on "product"
    alone again — the exact bug this function exists to prevent. Instead
    require ALL of the original query words (a phrase-level AND) — "Product
    Manager" still matches "Senior Product Manager" (both words present)
    but not a title with only one of them.
    """
    terms = _query_terms(query)
    if not terms:
        return True
    title_words = set(re.findall(r"[a-z0-9+#]+", (title or "").lower()))
    specific_terms = [t for t in terms if t not in _QUALIFIER_WORDS]
    if specific_terms:
        return any(term in title_words for term in specific_terms)
    return all(term in title_words for term in terms)


# ── Adzuna Fetcher ────────────────────────────────────────────────────────────
class AdzunaFetcher:
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self):
        self.app_id = settings.adzuna_app_id
        self.app_key = settings.adzuna_app_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch(self, query: str = "designer", country: str = "in", pages: int = 3, where: Optional[str] = None) -> list[dict]:
        """Fetch jobs from Adzuna API. `country` must be one of Adzuna's
        country endpoints (ADZUNA_COUNTRIES); `where` narrows to a city/
        region within it."""
        if not self.app_id or not self.app_key:
            logger.warning("⚠️  Adzuna API keys not set — skipping")
            return []
        if country not in ADZUNA_COUNTRIES:
            logger.info(f"   Adzuna has no '{country}' endpoint — skipping Adzuna for this fetch")
            return []
        if not check_budget("adzuna", settings.adzuna_daily_limit, amount=pages):
            return []

        jobs = []
        async with httpx.AsyncClient(timeout=30) as client:
            for page in range(1, pages + 1):
                try:
                    params = {
                        "app_id": self.app_id,
                        "app_key": self.app_key,
                        "what": query,
                        "results_per_page": 50,
                        "content-type": "application/json",
                    }
                    if where:
                        params["where"] = where
                    resp = await client.get(
                        f"{self.BASE_URL}/{country}/search/{page}",
                        params=params,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for job in data.get("results", []):
                        # Adzuna's `what` matching is fuzzy — results that
                        # share no meaningful query term get dropped here,
                        # BEFORE run_all_fetchers stamps search_category on
                        # them, because that stamp is trusted outright by
                        # the matcher's category gate. Same rule the free
                        # sources (Remotive/Greenhouse/Jobicy) always had.
                        if not _title_matches(job.get("title", ""), query):
                            continue
                        jobs.append(normalize_job(
                            source="adzuna",
                            external_id=job.get("id", ""),
                            title=job.get("title", ""),
                            company=job.get("company", {}).get("display_name", ""),
                            location=job.get("location", {}).get("display_name", ""),
                            description=job.get("description", ""),
                            source_url=job.get("redirect_url", ""),
                            salary_min=int(job["salary_min"]) if job.get("salary_min") else None,
                            salary_max=int(job["salary_max"]) if job.get("salary_max") else None,
                            posted_at=job.get("created"),
                        ))
                    logger.info(f"Adzuna page {page}: {len(data.get('results', []))} jobs")
                except Exception as e:
                    logger.error(f"❌ Adzuna page {page} failed: {e}")
                    break

        return jobs


# ── JSearch Fetcher (LinkedIn via RapidAPI) ───────────────────────────────────
class JSearchFetcher:
    # RapidAPI letscrape JSearch v5 — endpoint is /search
    BASE_URL = "https://jsearch.p.rapidapi.com/search"
    HOST = "jsearch.p.rapidapi.com"

    def __init__(self):
        self.api_key = settings.jsearch_api_key

    async def fetch(self, query: str = "UI UX Designer", num_pages: int = 1, location_text: Optional[str] = None) -> list[dict]:
        """Fetch jobs from JSearch (LinkedIn) via RapidAPI. `location_text`
        is free text ("Dubai", "London") appended as "in {location}";
        without one, the historical India default is kept so existing
        (mostly-India) users' results don't shift underneath them."""
        if not self.api_key:
            logger.warning("⚠️  JSearch API key not set — skipping")
            return []
        if not check_budget("jsearch", settings.jsearch_daily_limit, amount=num_pages):
            return []

        search_query = f"{query} in {location_text}" if location_text else f"{query} India"
        jobs = []
        async with httpx.AsyncClient(timeout=30) as client:
            for page in range(1, num_pages + 1):
                try:
                    resp = await client.get(
                        self.BASE_URL,
                        headers={
                            "X-RapidAPI-Key": self.api_key,
                            "X-RapidAPI-Host": self.HOST,
                        },
                        params={
                            "query": search_query,
                            "page": str(page),
                            "num_pages": "1",
                            "date_posted": "week",
                        },
                    )
                    if resp.status_code == 404:
                        logger.warning(f"⚠️  JSearch 404 — endpoint not available on your subscription plan")
                        break
                    resp.raise_for_status()
                    data = resp.json()

                    for job in data.get("data", []):
                        # Same fuzzy-source rule as Adzuna above: no query
                        # term in the title -> never stored, never stamped.
                        if not _title_matches(job.get("job_title", ""), query):
                            continue
                        apply_url = job.get("job_apply_link") or job.get("job_url") or ""
                        # JSearch is the one source with a structured
                        # experience field — prefer it over description
                        # parsing when present and positive.
                        req_exp = (job.get("job_required_experience") or {}).get("required_experience_in_months")
                        try:
                            req_exp = int(req_exp) if req_exp else None
                        except (TypeError, ValueError):
                            req_exp = None
                        jobs.append(normalize_job(
                            source="jsearch",
                            external_id=job.get("job_id", ""),
                            title=job.get("job_title", ""),
                            company=job.get("employer_name", ""),
                            location=f"{job.get('job_city', '')} {job.get('job_country', '')}".strip(),
                            description=job.get("job_description", ""),
                            source_url=apply_url or f"jsearch_{job.get('job_id', '')}",
                            salary_min=job.get("job_min_salary"),
                            salary_max=job.get("job_max_salary"),
                            employment_type=job.get("job_employment_type"),
                            is_remote=job.get("job_is_remote", False),
                            posted_at=job.get("job_posted_at_datetime_utc"),
                            required_experience_months=req_exp,
                        ))
                    logger.info(f"JSearch page {page}: {len(data.get('data', []))} jobs")
                except Exception as e:
                    logger.error(f"❌ JSearch page {page} failed: {e}")
                    break

        return jobs


# ── Remotive Fetcher (Free — Remote Jobs) ────────────────────────────────────
class RemotiveFetcher:
    BASE_URL = "https://remotive.com/api/remote-jobs"

    async def fetch(self, query: str = "", limit: int = 100) -> list[dict]:
        """Fetch remote jobs from Remotive (no API key needed), filtered by query."""
        jobs = []
        try:
            params: dict = {"limit": limit}
            if query:
                params["search"] = query
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

                for job in data.get("jobs", []):
                    if not _title_matches(job.get("title", ""), query):
                        continue

                    jobs.append(normalize_job(
                        source="remotive",
                        external_id=str(job.get("id", "")),
                        title=job.get("title", ""),
                        company=job.get("company_name", ""),
                        location=job.get("candidate_required_location", "Remote"),
                        description=job.get("description", ""),
                        source_url=job.get("url", ""),
                        employment_type=job.get("job_type", "full_time"),
                        is_remote=True,
                        posted_at=job.get("publication_date"),
                    ))

            logger.info(f"Remotive: {len(jobs)} jobs fetched")
        except Exception as e:
            logger.error(f"❌ Remotive fetch failed: {e}")
        return jobs


# ── Greenhouse Fetcher (Free — Startup/Tech Companies) ───────────────────────
class GreenhouseFetcher:
    BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    # Indian + global design-heavy companies on Greenhouse
    COMPANY_SLUGS = [
        "razorpay", "swiggy", "meesho", "cred", "zepto",
        "groww", "postman", "browserstack", "freshworks",
        "figma", "notion", "canva", "linear", "vercel",
    ]

    async def fetch(self, query: str = "") -> list[dict]:
        """Fetch jobs from Greenhouse-powered company career pages (no API key)."""
        jobs = []

        async with httpx.AsyncClient(timeout=20) as client:
            for slug in self.COMPANY_SLUGS:
                try:
                    resp = await client.get(
                        self.BASE_URL.format(slug=slug),
                        params={"content": "true"},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()

                    for job in data.get("jobs", []):
                        title = job.get("title", "")
                        if not _title_matches(title, query):
                            continue

                        location = ""
                        offices = job.get("offices") or job.get("location") or {}
                        if isinstance(offices, list) and offices:
                            location = offices[0].get("name", "")
                        elif isinstance(offices, dict):
                            location = offices.get("name", "")

                        apply_url = job.get("absolute_url", "")
                        jobs.append(normalize_job(
                            source="greenhouse",
                            external_id=str(job.get("id", "")),
                            title=title,
                            company=slug.capitalize(),
                            location=location,
                            description=job.get("content", ""),
                            source_url=apply_url,
                            posted_at=job.get("updated_at"),
                        ))

                except Exception as e:
                    logger.debug(f"Greenhouse {slug}: {e}")
                    continue

        logger.info(f"Greenhouse: {len(jobs)} jobs fetched")
        return jobs


# ── Jobicy Fetcher (Free — Remote Tech/Design) ────────────────────────────────
class JobicyFetcher:
    BASE_URL = "https://jobicy.com/api/v2/remote-jobs"

    async def fetch(self, query: str = "", count: int = 100) -> list[dict]:
        """Fetch remote jobs from Jobicy (no API key needed), filtered by query."""
        jobs = []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={"count": count},
                    headers={"User-Agent": "Mozilla/5.0 AI-Career-Copilot/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()

                for job in data.get("jobs", []):
                    title = job.get("jobTitle", "")
                    if not _title_matches(title, query):
                        continue

                    apply_url = job.get("url") or job.get("jobExcerpt", "")
                    jobs.append(normalize_job(
                        source="jobicy",
                        external_id=str(job.get("id", "")),
                        title=title,
                        company=job.get("companyName", ""),
                        location=job.get("jobGeo", "Remote"),
                        description=job.get("jobExcerpt", ""),
                        source_url=apply_url,
                        employment_type=job.get("jobType", ""),
                        is_remote=True,
                        posted_at=job.get("pubDate"),
                    ))

            logger.info(f"Jobicy: {len(jobs)} jobs fetched")
        except Exception as e:
            logger.error(f"❌ Jobicy fetch failed: {e}")
        return jobs


# ── Deduplication & Storage ───────────────────────────────────────────────────
# Columns added after launch — a database that hasn't run their migration
# yet must not lose every fetched job over one of them. Newest first, so
# the retry loop peels them off in reverse-migration order. Matching
# degrades gracefully on rows missing either (text fallback / "unknown
# experience" respectively).
_OPTIONAL_JOB_COLUMNS = ("required_experience_months", "search_category")


async def store_jobs(jobs: list[dict]) -> int:
    """
    Upsert jobs into the central jobs table.
    Uses source_url as the unique key to prevent duplicates.
    Returns the number of new jobs inserted.
    """
    if not jobs:
        return 0

    supabase = get_supabase()
    attempt_jobs = jobs
    stripped: list[str] = []
    to_strip = list(_OPTIONAL_JOB_COLUMNS)
    while True:
        try:
            response = (
                supabase.table("jobs")
                .upsert(attempt_jobs, on_conflict="source_url", ignore_duplicates=True)
                .execute()
            )
            count = len(response.data) if response.data else 0
            suffix = f" (without {', '.join(stripped)})" if stripped else ""
            logger.info(f"✅ Stored {count} new jobs{suffix} (out of {len(jobs)} fetched)")
            return count
        except Exception as e:
            # Peel off the next optional column actually present and retry.
            col = next((c for c in to_strip if any(c in j for j in attempt_jobs)), None)
            if col is None:
                logger.error(f"❌ Failed to store jobs: {e}")
                raise
            to_strip.remove(col)
            stripped.append(col)
            logger.warning(f"⚠️  Upsert failed ({e}) — retrying without '{col}'.")
            attempt_jobs = [{k: v for k, v in j.items() if k != col} for j in attempt_jobs]


# ── Main Runner ───────────────────────────────────────────────────────────────
async def run_all_fetchers(query: str = "", category: str = "", location: Optional[dict] = None) -> int:
    """
    Run all fetchers and store results. Returns total new jobs stored.

    `category` (the user job_category this query was built for, e.g.
    'fullstack_developer') is stamped onto every job as search_category —
    core/matcher.py uses this tag to stop a job from one profession being
    matched to a user in a completely different one, regardless of how
    high its similarity/keyword score happens to come out. Jobs upserted
    on a source_url that already exists keep their original tag (upsert
    with ignore_duplicates=True never overwrites), which is fine — the
    tag only needs to be right the first time a job is ever stored.

    `location` is a resolve_fetch_location() dict (or None for the
    historical India default). It steers the location-capable sources:
    Adzuna's country endpoint + `where` city, JSearch's query text. The
    remote-only sources (Remotive/Jobicy) and Greenhouse (global company
    boards) are location-independent and run unchanged.
    """
    logger.info(f"🔍 Starting job fetch for query: '{query}'" + (f" @ {location['raw']}" if location else ""))

    adzuna = AdzunaFetcher()
    jsearch = JSearchFetcher()
    remotive = RemotiveFetcher()
    greenhouse = GreenhouseFetcher()
    jobicy = JobicyFetcher()

    if location is None:
        adzuna_country, adzuna_where, jsearch_location = "in", None, None  # historical default
    else:
        # An unresolvable country must SKIP Adzuna (its API is per-country-
        # endpoint), not silently fall back to India-results-for-a-Dubai-user.
        # "unknown" is deliberately not in ADZUNA_COUNTRIES, so fetch() skips.
        adzuna_country = location.get("country_code") or "unknown"
        adzuna_where = location.get("city")
        jsearch_location = location.get("city") or location.get("raw")

    # Run all fetchers concurrently — the query drives every source now, so the
    # free (no-key) sources work for any profession, not just design.
    results = await asyncio.gather(
        adzuna.fetch(query=query, country=adzuna_country, where=adzuna_where),
        jsearch.fetch(query=query, location_text=jsearch_location),
        remotive.fetch(query=query),
        greenhouse.fetch(query=query),
        jobicy.fetch(query=query),
        return_exceptions=True,
    )

    adzuna_jobs    = results[0] if not isinstance(results[0], Exception) else []
    jsearch_jobs   = results[1] if not isinstance(results[1], Exception) else []
    remotive_jobs  = results[2] if not isinstance(results[2], Exception) else []
    greenhouse_jobs= results[3] if not isinstance(results[3], Exception) else []
    jobicy_jobs    = results[4] if not isinstance(results[4], Exception) else []

    all_jobs = adzuna_jobs + jsearch_jobs + remotive_jobs + greenhouse_jobs + jobicy_jobs
    logger.info(
        f"📦 Total fetched: {len(all_jobs)} jobs "
        f"({len(adzuna_jobs)} Adzuna + {len(jsearch_jobs)} JSearch + "
        f"{len(remotive_jobs)} Remotive + {len(greenhouse_jobs)} Greenhouse + "
        f"{len(jobicy_jobs)} Jobicy)"
    )

    if category:
        for job in all_jobs:
            job["search_category"] = category

    return await store_jobs(all_jobs)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    total = asyncio.run(run_all_fetchers())
    print(f"\n🎉 Done! {total} new jobs stored in database.")
