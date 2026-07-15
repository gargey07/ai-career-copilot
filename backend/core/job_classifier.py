"""
AI Job Requirement Classifier
──────────────────────────────
Fallback experience/seniority extraction for jobs a hand-written parser
structurally can't cover — phrasing like "recent graduates welcome"
(implies entry-level, no digit anywhere) or "you'll mentor junior
engineers" (implies senior) that no regex/keyword list can enumerate.

Deliberately a JOB-level classifier, not a per-user gate: it runs ONCE
per job and writes the result to jobs.required_experience_months /
jobs.seniority_level — the exact same columns core/matcher.py's already-
tested _experience_ok gate reads. Running an LLM per (user × job) for the
dashboard list instead would multiply into hundreds of calls/day against
a budget already spent on resume generation + core/recruiter.py's
per-match evals; classifying each job once and feeding the existing
correct gate math costs one call per AMBIGUOUS job, ever.

Only ever called for jobs where the free, instant pass already came up
empty (jobs/fetchers.py's experience_months_from_text +
infer_seniority_level) — see core/pipeline_runner.py's
_classify_unknown_experience_jobs. Never a replacement for that pass,
only its fallback.

Failure contract (same as every AI stage in this codebase):
classify_job returns None on ANY failure — budget exhausted, provider
down, unparseable output. Callers must treat None as "still unknown,"
never invent a value.
"""
from __future__ import annotations
import json
import logging
import re

from core.ai import get_ai_provider
from core.config import get_settings
from core.usage_guard import check_budget

logger = logging.getLogger(__name__)
settings = get_settings()

SENIORITY_LEVELS = ("entry", "mid", "senior", "lead")

# Descriptions are usually the informative part; titles rarely carry more
# than what jobs/fetchers.py's infer_seniority_level already extracts for
# free. Same truncation budget as recruiter.py's job description slice.
_MAX_DESCRIPTION_CHARS = 3000

CLASSIFY_JOB_PROMPT = """
You are extracting structured hiring requirements from a job posting.

Given the title and description below, determine:
1. The MINIMUM years of experience required, in months (e.g. 2 years = 24).
   Infer this from ANY signal in the text, not just explicit "N years"
   phrasing — "recent graduates welcome" or "no prior experience needed"
   implies entry-level (0 months); "you'll mentor junior engineers" or
   "deep expertise" implies senior (60+ months); a plain listing with
   truly no seniority signal at all should be null.
2. The seniority band: one of "entry", "mid", "senior", "lead", or null
   if genuinely unclear.

Respond with ONLY a JSON object, no markdown, in exactly this shape:
{{"required_experience_months": <int or null>, "seniority_level": "<entry|mid|senior|lead>" or null}}

---

TITLE: {title}
DESCRIPTION:
{description}
"""


def parse_classification(raw: str) -> dict | None:
    """
    Normalize a model response into {"required_experience_months": int|None,
    "seniority_level": str|None}, or None when the response can't be
    trusted at all. Tolerates markdown fences / prose around the JSON,
    same shape as core/recruiter.py's parse_eval.
    """
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    months = data.get("required_experience_months")
    try:
        months = int(months) if months is not None else None
        if months is not None and (months <= 0 or months > 40 * 12):
            months = None  # same implausibility guard as the regex parser
    except (TypeError, ValueError):
        months = None

    level = str(data.get("seniority_level") or "").strip().lower()
    if level not in SENIORITY_LEVELS:
        level = None

    if months is None and level is None:
        return None  # nothing usable — treat as a failed classification

    return {"required_experience_months": months, "seniority_level": level}


async def classify_job(job: dict) -> dict | None:
    """
    Run the AI fallback classification for one job. Returns the
    normalized dict, or None on any failure (budget, provider, or an
    unparseable/empty response) — callers must leave the job's columns
    untouched in that case, never write a guess.
    """
    title = (job.get("title") or "").strip()
    description = (job.get("description") or "").strip()
    if not title and not description:
        return None

    if not check_budget("job_classify", settings.job_classify_daily_limit):
        return None

    prompt = CLASSIFY_JOB_PROMPT.format(title=title, description=description[:_MAX_DESCRIPTION_CHARS])

    try:
        ai = get_ai_provider()
        raw = await ai.generate_text(prompt, temperature=0.1)
    except Exception as e:
        logger.info(f"   Job classification unavailable ({e}) — leaving as unknown.")
        return None

    result = parse_classification(raw)
    if result is None:
        logger.info(f"   Job classification returned unparseable output for {job.get('id')} — leaving as unknown.")
    return result


# How much application-page text to hand the AI classifier when the free
# regex found nothing on the page either — enough to cover an ATS page's
# requirements block without blowing the prompt budget.
_MAX_PAGE_TEXT_FOR_AI_CHARS = 2000


async def resolve_job_experience(job: dict) -> dict | None:
    """
    Full experience-resolution ladder for one still-unknown job, cheapest
    step first:

    1. Fetch the job's own application page (jobs/fetchers.py's
       fetch_job_page_text) and run the FREE regex on its visible text —
       many Adzuna listings state the requirement ONLY there ("Required
       Experience: 2 - 5 Years" on the company's ATS page), never in the
       truncated description the API returned. Costs one HTTP GET, no AI.
    2. AI classification (classify_job) — with the page text appended to
       the description when we got any, so the model sees the same
       content a human clicking Apply sees.

    Returns the same {"required_experience_months", "seniority_level"}
    shape as classify_job, or None when every rung came up empty. Same
    contract as everything else in this module: None means "still
    unknown, leave the row untouched", never an error.
    """
    from jobs.fetchers import experience_months_from_text, fetch_job_page_text

    page_text = await fetch_job_page_text(job.get("source_url") or "")
    if page_text:
        months = experience_months_from_text(page_text)
        if months:
            logger.info(f"   📄 Application page stated the requirement for job {job.get('id')}: {months} months")
            return {"required_experience_months": months, "seniority_level": None}

    job_for_ai = dict(job)
    if page_text:
        job_for_ai["description"] = (
            (job.get("description") or "")
            + "\n\nText from the job's application page:\n"
            + page_text[:_MAX_PAGE_TEXT_FOR_AI_CHARS]
        ).strip()
    return await classify_job(job_for_ai)
