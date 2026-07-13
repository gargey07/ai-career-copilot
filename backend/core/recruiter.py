"""
AI Recruiter Evaluation
───────────────────────
One structured AI call per resume-generation candidate that answers the
question no keyword/embedding stage can: "would a recruiter realistically
interview this person for this job?"

This is the comprehension layer the matching pipeline lacked — category
tags, token gates, and cosine similarity all operate on words, so a
Product Designer job that shares surface vocabulary with a developer
profile can survive every earlier filter. The evaluator actually reads
the job description against the resume and returns a verdict plus the
recruiter-style reasoning behind it (strengths / missing skills / risks),
which the dashboard shows verbatim — recommendations must never feel
like a black box (docs/PRODUCT_STRATEGY_BETA.md, Transparency).

Deliberately NOT returned: any "interview probability" percentage. An
LLM cannot know that number, and Product Value #1 forbids decorative
statistics. `fit_score` is stored for ranking/debugging but the verdict
+ written reason are the product surface.

Failure contract (same as every pipeline stage): evaluate_match returns
None on ANY failure — budget exhausted, provider down, unparseable
output — and callers treat None as "no gate". An AI hiccup must never
mean "no resumes today".
"""
from __future__ import annotations
import json
import logging
import re

from core.ai import get_ai_provider

logger = logging.getLogger(__name__)

VERDICTS = ("apply", "stretch", "skip")

# Description/resume truncation mirrors optimizer.py's prompt budgeting.
_MAX_DESCRIPTION_CHARS = 3000
_MAX_RESUME_CHARS = 4000

RECRUITER_EVAL_PROMPT = """
You are an experienced technical recruiter screening candidates.

Given the candidate profile and the job below, evaluate whether this
candidate would realistically be invited to interview for this job.

Rules:
- Judge the CORE PROFESSION first: if the job's primary discipline is
  different from the candidate's (e.g. a design role for a software
  developer, a sales role for a data analyst), the verdict is "skip"
  regardless of surface keyword overlap.
- "apply": the candidate meets the core requirements — a recruiter would
  plausibly shortlist them.
- "stretch": same profession and a real chance, but with meaningful gaps
  (missing skills, slightly under the experience bar).
- "skip": wrong profession, or requirements the candidate demonstrably
  cannot meet (e.g. needs 5+ years of a discipline absent from the resume).
- Base everything ONLY on what is in the resume and job description.
  Never invent candidate experience.
- strengths/missing/risks: short concrete phrases (e.g. "FastAPI",
  "no AWS experience"), not sentences.

Respond with ONLY a JSON object, no markdown, in exactly this shape:
{{"verdict": "apply|stretch|skip", "fit_score": 0-100, "strengths": ["..."], "missing": ["..."], "risks": ["..."], "reason": "2-3 plain sentences a job seeker can understand"}}

---

CANDIDATE
Target roles: {target_roles}
Experience level: {experience_level}
Resume:
{resume_text}

---

JOB
Title: {job_title}
Company: {company}
Description:
{job_description}
"""


def parse_eval(raw: str) -> dict | None:
    """
    Normalize a model response into the stored eval dict, or None when it
    can't be trusted. Tolerates markdown code fences and prose around the
    JSON (smaller waterfall models add both), but rejects anything without
    a valid verdict — a gate must never act on a guess.
    """
    if not raw:
        return None
    text = raw.strip()
    # ```json ... ``` fences, with or without the language tag.
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    # Prose-wrapped JSON: take the outermost object.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in VERDICTS:
        return None

    def _phrases(key: str) -> list[str]:
        value = data.get(key)
        if not isinstance(value, list):
            return []
        return [str(v).strip() for v in value if str(v).strip()][:8]

    fit_score = data.get("fit_score")
    try:
        fit_score = max(0, min(100, int(fit_score)))
    except (TypeError, ValueError):
        fit_score = None

    return {
        "verdict": verdict,
        "fit_score": fit_score,
        "strengths": _phrases("strengths"),
        "missing": _phrases("missing"),
        "risks": _phrases("risks"),
        "reason": str(data.get("reason") or "").strip()[:1000],
    }


async def evaluate_match(user: dict, job: dict) -> dict | None:
    """
    Run the recruiter evaluation for one user+job. Returns the normalized
    eval dict, or None on any failure (no gate — see module docstring).
    """
    resume_text = (user.get("resume_text") or "").strip()
    description = (job.get("description") or "").strip()
    if not resume_text or not description:
        # Nothing substantive to judge — an eval here would be noise.
        return None

    prompt = RECRUITER_EVAL_PROMPT.format(
        target_roles=", ".join(user.get("target_roles") or []) or "Not specified",
        experience_level=user.get("experience_level") or "Not specified",
        resume_text=resume_text[:_MAX_RESUME_CHARS],
        job_title=job.get("title") or "",
        company=job.get("company") or "",
        job_description=description[:_MAX_DESCRIPTION_CHARS],
    )

    try:
        ai = get_ai_provider()
        raw = await ai.generate_text(prompt, temperature=0.1)
    except Exception as e:
        logger.warning(f"   Recruiter eval unavailable ({e}) — proceeding without a gate.")
        return None

    result = parse_eval(raw)
    if result is None:
        logger.warning(f"   Recruiter eval returned unparseable output — proceeding without a gate. Raw head: {raw[:200]!r}")
        return result
    logger.info(
        f"   🧑‍💼 Recruiter eval: {result['verdict']} "
        f"({result['fit_score']}) — {job.get('title')} @ {job.get('company')}"
    )
    return result
