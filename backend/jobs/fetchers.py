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
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings
from core.usage_guard import check_budget
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()


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
) -> dict:
    """Normalize any job from any source into a common schema."""
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
        "posted_at": posted_at,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Adzuna Fetcher ────────────────────────────────────────────────────────────
class AdzunaFetcher:
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self):
        self.app_id = settings.adzuna_app_id
        self.app_key = settings.adzuna_app_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch(self, query: str = "designer", country: str = "in", pages: int = 3) -> list[dict]:
        """Fetch jobs from Adzuna API."""
        if not self.app_id or not self.app_key:
            logger.warning("⚠️  Adzuna API keys not set — skipping")
            return []
        if not check_budget("adzuna", settings.adzuna_daily_limit, amount=pages):
            return []

        jobs = []
        async with httpx.AsyncClient(timeout=30) as client:
            for page in range(1, pages + 1):
                try:
                    resp = await client.get(
                        f"{self.BASE_URL}/{country}/search/{page}",
                        params={
                            "app_id": self.app_id,
                            "app_key": self.app_key,
                            "what": query,
                            "results_per_page": 50,
                            "content-type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for job in data.get("results", []):
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

    async def fetch(self, query: str = "UI UX Designer", num_pages: int = 1) -> list[dict]:
        """Fetch jobs from JSearch (LinkedIn) via RapidAPI."""
        if not self.api_key:
            logger.warning("⚠️  JSearch API key not set — skipping")
            return []
        if not check_budget("jsearch", settings.jsearch_daily_limit, amount=num_pages):
            return []

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
                            "query": f"{query} India",
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
                        title_lower = job.get("job_title", "").lower()
                        seniority = (
                            "senior" if "senior" in title_lower else
                            "lead" if "lead" in title_lower else
                            "entry" if any(w in title_lower for w in ("junior", "intern", "fresher")) else
                            "mid"
                        )
                        apply_url = job.get("job_apply_link") or job.get("job_url") or ""
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
                            seniority_level=seniority,
                            is_remote=job.get("job_is_remote", False),
                            posted_at=job.get("job_posted_at_datetime_utc"),
                        ))
                    logger.info(f"JSearch page {page}: {len(data.get('data', []))} jobs")
                except Exception as e:
                    logger.error(f"❌ JSearch page {page} failed: {e}")
                    break

        return jobs


# ── Remotive Fetcher (Free — Remote Jobs) ────────────────────────────────────
class RemotiveFetcher:
    BASE_URL = "https://remotive.com/api/remote-jobs"

    async def fetch(self, category: str = "Design", limit: int = 50) -> list[dict]:
        """Fetch remote design jobs from Remotive (no API key needed)."""
        jobs = []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={"category": category, "limit": limit},
                )
                resp.raise_for_status()
                data = resp.json()

                for job in data.get("jobs", []):
                    title_lower = (job.get("title") or "").lower()
                    is_design = any(w in title_lower for w in (
                        "ui", "ux", "design", "figma", "product designer",
                        "visual", "interface", "interaction"
                    ))
                    if not is_design:
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

            logger.info(f"Remotive: {len(jobs)} design jobs fetched")
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

    async def fetch(self, query: str = "designer") -> list[dict]:
        """Fetch jobs from Greenhouse-powered company career pages (no API key)."""
        jobs = []
        query_lower = query.lower()

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
                        title_lower = title.lower()
                        # Filter to design roles only
                        if not any(w in title_lower for w in (
                            "ui", "ux", "design", "product designer",
                            "visual", "interface", "interaction", "figma"
                        )):
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

        logger.info(f"Greenhouse: {len(jobs)} design jobs fetched")
        return jobs


# ── Jobicy Fetcher (Free — Remote Tech/Design) ────────────────────────────────
class JobicyFetcher:
    BASE_URL = "https://jobicy.com/api/v2/remote-jobs"

    async def fetch(self, tag: str = "design", count: int = 50) -> list[dict]:
        """Fetch remote design jobs from Jobicy (no API key needed)."""
        jobs = []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={"count": count, "tag": tag},
                    headers={"User-Agent": "Mozilla/5.0 AI-Career-Copilot/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()

                for job in data.get("jobs", []):
                    title = job.get("jobTitle", "")
                    title_lower = title.lower()
                    if not any(w in title_lower for w in (
                        "ui", "ux", "design", "figma", "product designer",
                        "visual", "interface"
                    )):
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

            logger.info(f"Jobicy: {len(jobs)} design jobs fetched")
        except Exception as e:
            logger.error(f"❌ Jobicy fetch failed: {e}")
        return jobs


# ── Deduplication & Storage ───────────────────────────────────────────────────
async def store_jobs(jobs: list[dict]) -> int:
    """
    Upsert jobs into the central jobs table.
    Uses source_url as the unique key to prevent duplicates.
    Returns the number of new jobs inserted.
    """
    if not jobs:
        return 0

    supabase = get_supabase()
    try:
        response = (
            supabase.table("jobs")
            .upsert(jobs, on_conflict="source_url", ignore_duplicates=True)
            .execute()
        )
        count = len(response.data) if response.data else 0
        logger.info(f"✅ Stored {count} new jobs (out of {len(jobs)} fetched)")
        return count
    except Exception as e:
        logger.error(f"❌ Failed to store jobs: {e}")
        raise


# ── Main Runner ───────────────────────────────────────────────────────────────
async def run_all_fetchers(query: str = "UI UX Designer") -> int:
    """Run all fetchers and store results. Returns total new jobs stored."""
    logger.info(f"🔍 Starting job fetch for query: '{query}'")

    adzuna = AdzunaFetcher()
    jsearch = JSearchFetcher()
    remotive = RemotiveFetcher()
    greenhouse = GreenhouseFetcher()
    jobicy = JobicyFetcher()

    # Run all fetchers concurrently
    results = await asyncio.gather(
        adzuna.fetch(query=query),
        jsearch.fetch(query=query),
        remotive.fetch(),
        greenhouse.fetch(query=query),
        jobicy.fetch(),
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

    return await store_jobs(all_jobs)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    total = asyncio.run(run_all_fetchers())
    print(f"\n🎉 Done! {total} new jobs stored in database.")
