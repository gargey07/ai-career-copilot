"""
AI Resume & Cover Letter Optimizer
────────────────────────────────────
Generates ATS-optimized resumes and personalized cover letters
using the AI provider abstraction layer.

Only called for the TOP 3 matched jobs per user — cost optimization.

Run standalone:
    python core/optimizer.py
"""
import logging
from datetime import date, timedelta

from core.ai import get_ai_provider
from core.config import get_settings
from core.skill_maps import expand_skills, match_skills_to_job
from core.usage_guard import BudgetExceededError
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Prompts ───────────────────────────────────────────────────────────────────
RESUME_OPTIMIZATION_PROMPT = """
You are an expert ATS resume optimizer and career coach.

Your task:
Rewrite the user's resume to be perfectly tailored for the job below.

Rules:
- NEVER invent experience, skills, or achievements that aren't in the original resume.
- ONLY rearrange, rephrase, and highlight existing content to better match the job.
- Inject relevant keywords from the job description naturally.
- Rewrite the summary to speak directly to this role and company.
- In the SKILLS section, use the EXPANDED SKILLS LIST provided — reorder to put the most relevant skills first based on the job description.
- Keep the same sections: Summary, Experience, Skills, Education.
- Keep it concise — 1 page equivalent of content.
- Output plain text only — NO markdown, NO asterisks, NO bold markers.

---

JOB TITLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION:
{job_description}

---

ORIGINAL RESUME:
{resume_text}

---

EXPANDED SKILLS LIST (use these in the Skills section, reordered by relevance):
{expanded_skills}

SKILLS THAT MATCH THIS JOB WELL:
{matched_skills}

---

OUTPUT FORMAT (plain text, no markdown). Follow this structure EXACTLY —
every experience and education entry starts with ONE header line using
" | " separators. If a date or year is missing in the original resume,
leave that field empty; NEVER write placeholders like "( - )" or "N/A".

SUMMARY
[rewritten 3-4 line summary]

PROFESSIONAL EXPERIENCE
[Job Title] | [Company] | [Dates if known]
- [achievement bullet with job-relevant keywords]
- [achievement bullet]

SKILLS
Tools: [comma-separated, most job-relevant first]
Skills: [comma-separated, most job-relevant first]

EDUCATION
[Degree] | [School] | [Year if known]
"""

COVER_LETTER_PROMPT = """
You are an expert career coach writing a personalized cover letter.

Rules:
- Keep it under 300 words.
- Reference specific things from the job description and company.
- Match the tone to the role (formal for corporate, conversational for startups).
- Never use generic filler phrases like "I am writing to express my interest."
- Start with a compelling, specific opening line.

---

APPLICANT NAME: {name}
TARGET ROLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION:
{job_description}

RESUME SUMMARY:
{resume_summary}

---

Write the cover letter now:
"""


# ── Optimizer Functions ───────────────────────────────────────────────────────
async def optimize_resume(
    resume_text: str,
    job_title: str,
    company: str,
    job_description: str,
    user_tools: list[str] = None,
    user_skills: list[str] = None,
    job_category: str = "ui_ux_designer",
) -> str:
    """Rewrite a resume to be tailored for a specific job."""
    ai = get_ai_provider()

    skill_data = match_skills_to_job(
        user_tools or [],
        user_skills or [],
        job_description,
        job_category,
    )
    expanded_tools  = ", ".join(skill_data["expanded_tools"]) or "See resume"
    expanded_skills = ", ".join(skill_data["expanded_skills"]) or "See resume"
    matched         = ", ".join(skill_data["matched_skills"]) or "None detected"
    expanded = f"Tools: {expanded_tools}\nSkills: {expanded_skills}"

    prompt = RESUME_OPTIMIZATION_PROMPT.format(
        job_title=job_title,
        company=company,
        job_description=job_description[:3000],
        resume_text=resume_text,
        expanded_skills=expanded,
        matched_skills=matched,
    )

    logger.info(f"🤖 Optimizing resume for: {job_title} @ {company}")
    return await ai.generate_text(prompt, temperature=0.2)


async def generate_cover_letter(
    name: str,
    resume_text: str,
    job_title: str,
    company: str,
    job_description: str,
) -> str:
    """Generate a personalized cover letter for a specific job."""
    ai = get_ai_provider()

    # Extract summary from resume (first 500 chars is usually good)
    resume_summary = resume_text[:500]

    prompt = COVER_LETTER_PROMPT.format(
        name=name,
        job_title=job_title,
        company=company,
        job_description=job_description[:2000],
        resume_summary=resume_summary,
    )

    logger.info(f"✍️  Generating cover letter for: {job_title} @ {company}")
    return await ai.generate_text(prompt, temperature=0.5)


# How far back to reuse an already-generated resume for the same user+job.
# The freshness logic re-surfaces a job at most every few days on a small
# job pool — regenerating an identical resume for it costs a full AI call
# for byte-identical output.
RESUME_CACHE_DAYS = 7


def _find_recent_resume(supabase, user_id: str, job_id: str, today: str) -> dict | None:
    """Most recent prior match of the same user+job (within RESUME_CACHE_DAYS)
    that already has generated resume text. Best-effort — any failure just
    means a fresh AI call, never an error."""
    cutoff = (date.today() - timedelta(days=RESUME_CACHE_DAYS)).isoformat()
    try:
        resp = (
            supabase.table("user_jobs")
            .select("optimized_resume_text, cover_letter_text, pdf_url")
            .eq("user_id", user_id)
            .eq("job_id", job_id)
            .neq("digest_date", today)
            .gte("digest_date", cutoff)
            .not_.is_("optimized_resume_text", "null")
            .order("digest_date", desc=True)
            .limit(1)
            .execute()
        )
        return (resp.data or [None])[0]
    except Exception as e:
        logger.warning(f"   Resume-cache lookup failed ({e}) — generating fresh.")
        return None


def _apply_cached_resume(supabase, match_id: str, cached: dict) -> None:
    """Copy a prior generation onto today's row. The PDF is byte-identical
    for the same user+job, so a cached pdf_url skips the Chromium render
    too (the PDF generator selects on pdf_url IS NULL)."""
    payload = {
        "optimized_resume_text": cached["optimized_resume_text"],
        "cover_letter_text": cached.get("cover_letter_text"),
        "status": "pdf_ready" if cached.get("pdf_url") else "resume_ready",
    }
    if cached.get("pdf_url"):
        payload["pdf_url"] = cached["pdf_url"]
    try:
        supabase.table("user_jobs").update({**payload, "cache_hit": True}).eq("id", match_id).execute()
    except Exception:
        # cache_hit is a newer column — reuse must work without the migration.
        supabase.table("user_jobs").update(payload).eq("id", match_id).execute()


# ── Pipeline Function ─────────────────────────────────────────────────────────
async def run_optimizer_for_user(user_id: str) -> int:
    """
    Generate optimized resumes + cover letters for today's top matches.
    Only processes the top AI_JOBS_PER_USER jobs (default: 3) to save costs.

    Returns the number of resumes generated.
    """
    supabase = get_supabase()
    today = date.today().isoformat()

    # 1. Get user profile (resume_quota_override is a newer column — degrade
    #    to the global default pre-migration).
    base_fields = "name, resume_text, skills, tools, job_category"
    try:
        user_resp = supabase.table("users").select(f"{base_fields}, resume_quota_override").eq("id", user_id).single().execute()
    except Exception:
        user_resp = supabase.table("users").select(base_fields).eq("id", user_id).single().execute()
    if not user_resp.data or not user_resp.data.get("resume_text"):
        logger.warning(f"⚠️  User {user_id} has no resume text — skipping AI optimization")
        return 0

    user = user_resp.data
    # Per-user admin override (T-023) beats the global AI_JOBS_PER_USER cap.
    override = user.get("resume_quota_override")
    ai_limit = override if override is not None else settings.ai_jobs_per_user
    if ai_limit <= 0:
        logger.info(f"   Resume quota for user {user_id} is 0 — skipping AI optimization")
        return 0

    # 2. Get today's top matches (only top N for AI, ranked by match_score).
    #    Select by WORK REMAINING (no resume text yet), not by status: the
    #    digest email flips matches to 'emailed', and filtering on
    #    status='matched' alone permanently locked those out of resume
    #    generation — the "Resumes Ready: 0 forever" bug. 'pdf_failed' rows
    #    are excluded: they already have resume text and belong to the
    #    user-facing Retry path, not the optimizer.
    matches_resp = (
        supabase.table("user_jobs")
        .select("id, job_id, rank")
        .eq("user_id", user_id)
        .eq("digest_date", today)
        .is_("optimized_resume_text", "null")
        .in_("status", ["matched", "emailed"])
        .order("rank", desc=False)
        .limit(ai_limit)
        .execute()
    )
    matches = matches_resp.data or []

    if not matches:
        logger.info(f"   No unprocessed matches found for user {user_id} today")
        return 0

    # 3. For each top match, generate resume (+ cover letter when enabled)
    generated = 0
    for match in matches:
        # Reuse a recent generation for the same user+job before spending
        # an AI call (and possibly a Chromium render) on identical output.
        cached = _find_recent_resume(supabase, user_id, match["job_id"], today)
        if cached:
            try:
                _apply_cached_resume(supabase, match["id"], cached)
                generated += 1
                logger.info(f"   ♻️  Reused cached resume for job {match['job_id']} (no AI call)")
                continue
            except Exception as e:
                logger.warning(f"   Cache apply failed ({e}) — generating fresh.")

        job_resp = (
            supabase.table("jobs")
            .select("title, company, description")
            .eq("id", match["job_id"])
            .single()
            .execute()
        )
        if not job_resp.data:
            continue

        job = job_resp.data
        try:
            optimized_resume = await optimize_resume(
                resume_text=user["resume_text"],
                job_title=job["title"],
                company=job["company"],
                job_description=job.get("description", ""),
                user_tools=user.get("tools") or [],
                user_skills=user.get("skills") or [],
                job_category=user.get("job_category") or "ui_ux_designer",
            )

            # Cover letters are a full extra Gemini call per match and appear
            # nowhere user-facing yet (only the admin Inspect view) — off by
            # default; flip GENERATE_COVER_LETTERS=true when they ship in the
            # product. Halves per-user AI latency on the 0.1-CPU instance.
            cover_letter = None
            if settings.generate_cover_letters:
                cover_letter = await generate_cover_letter(
                    name=user.get("name", "Applicant"),
                    resume_text=user["resume_text"],
                    job_title=job["title"],
                    company=job["company"],
                    job_description=job.get("description", ""),
                )

            # Update the user_jobs record
            supabase.table("user_jobs").update({
                "optimized_resume_text": optimized_resume,
                "cover_letter_text": cover_letter,
                "status": "resume_ready",
            }).eq("id", match["id"]).execute()

            generated += 1
            logger.info(f"   ✅ Done: {job['title']} @ {job['company']}")

        except BudgetExceededError as e:
            logger.warning(f"   🚫 {e} — stopping AI generation for today.")
            break
        except Exception as e:
            logger.error(f"   ❌ Failed for {job.get('title', match['job_id'])}: {e}")

    logger.info(f"🏁 Optimizer done for user {user_id}: {generated}/{len(matches)} resumes generated")
    return generated


if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    print("ℹ️  Run this with a real user_id to test the optimizer:")
    print("   Modify the user_id below and re-run.")

    # Replace with a real user UUID from your Supabase users table
    TEST_USER_ID = "YOUR-USER-UUID-HERE"

    asyncio.run(run_optimizer_for_user(TEST_USER_ID))
