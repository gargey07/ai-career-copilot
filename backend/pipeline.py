"""
Main Pipeline — Orchestrates all steps in sequence
────────────────────────────────────────────────────
This is the daily driver that runs at 7 AM.

Execution order:
  1. Fetch jobs from all sources
  2. Match jobs to all active users
  3. Generate AI resumes + cover letters (top 3/user)
  4. Generate PDF resumes
  5. Send morning digest emails
  6. Log pipeline status

Run manually:
    python pipeline.py           # full run
    python pipeline.py --test    # 1 user, 3 jobs, fast
"""
import asyncio
import logging
import sys
import time
from datetime import date, datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from core.config import get_settings
from database.supabase_client import get_supabase
from jobs.fetchers import run_all_fetchers
from core.matcher import run_matching_for_all_users, match_jobs_for_user, store_matches
from core.skill_maps import get_search_queries
from core.optimizer import run_optimizer_for_user
from core.pdf_generator import run_pdf_generator_for_user
from core.email_sender import send_morning_digest

# Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/pipeline.log"),
    ],
)
logger = logging.getLogger(__name__)
settings = get_settings()


async def embed_unembedded_jobs(batch_size: int = 50) -> int:
    """Generate embeddings for all jobs that don't have one yet."""
    from core.ai import get_ai_provider
    supabase = get_supabase()
    ai = get_ai_provider()

    resp = supabase.table("jobs").select("id, title, company, description").is_("embedding", "null").limit(batch_size).execute()
    jobs = resp.data or []

    if not jobs:
        logger.info("   All jobs already embedded.")
        return 0

    logger.info(f"   Embedding {len(jobs)} jobs...")
    count = 0
    for job in jobs:
        try:
            text = f"{job['title']} at {job['company']}. {(job.get('description') or '')[:1000]}"
            embedding = await ai.embed_text(text)
            supabase.table("jobs").update({"embedding": embedding}).eq("id", job["id"]).execute()
            count += 1
        except Exception as e:
            logger.warning(f"   ⚠️  Failed to embed job {job['id']}: {e}")

    return count


async def run_pipeline(test_mode: bool = False):
    """
    Full pipeline execution.
    In test mode: uses 1 active user, matches 3 jobs, skips email.
    """
    start_time = time.time()
    supabase = get_supabase()
    today = date.today().isoformat()

    logger.info("=" * 60)
    logger.info(f"🚀 AI Career Copilot Pipeline Starting")
    logger.info(f"   Date: {today}  |  Mode: {'TEST' if test_mode else 'PRODUCTION'}")
    logger.info("=" * 60)

    # Track pipeline run
    run_record = {
        "run_date": today,
        "status": "running",
    }
    try:
        run_resp = supabase.table("pipeline_status").insert(run_record).execute()
        run_id = run_resp.data[0]["id"] if run_resp.data else None
    except Exception:
        run_id = None

    stats = {}

    # ── Step 1: Fetch Jobs (per unique job category across all users) ────────────
    logger.info("\n📡 STEP 1: Fetching Jobs")
    try:
        users_resp = supabase.table("users").select("job_category").eq("is_active", True).execute()
        categories = list({u.get("job_category") or "ui_ux_designer" for u in (users_resp.data or [])})
        total_fetched = 0
        for category in categories:
            queries = get_search_queries(category)
            for query in queries[:1]:  # use first query per category to avoid rate limits
                logger.info(f"   🔍 Fetching for category '{category}': {query}")
                count = await run_all_fetchers(query=query)
                total_fetched += count
        stats["jobs_fetched"] = total_fetched
        logger.info(f"   ✅ {total_fetched} new jobs stored across {len(categories)} categories")
    except Exception as e:
        logger.error(f"   ❌ Job fetch failed: {e}")
        stats["jobs_fetched"] = 0

    # ── Step 1.5: Embed Jobs ──────────────────────────────────────────────────
    logger.info("\n🧠 STEP 1.5: Embedding Jobs (for vector matching)")
    try:
        embedded = await embed_unembedded_jobs()
        logger.info(f"   ✅ {embedded} jobs embedded")
    except Exception as e:
        logger.error(f"   ❌ Job embedding failed: {e}")

    # ── Step 2: Match Jobs to Users ───────────────────────────────────────────
    logger.info("\n🎯 STEP 2: Matching Jobs to Users")
    try:
        matching_result = await run_matching_for_all_users()
        stats["jobs_matched"] = matching_result["total_matches"]
        stats["users_processed"] = matching_result["users_processed"]
        logger.info(f"   ✅ {matching_result['total_matches']} matches for {matching_result['users_processed']} users")
    except Exception as e:
        logger.error(f"   ❌ Matching failed: {e}")
        stats["jobs_matched"] = 0

    # ── Step 3: Generate AI Resumes ───────────────────────────────────────────
    logger.info("\n🤖 STEP 3: Generating AI Resumes")
    total_resumes = 0
    try:
        users_resp = supabase.table("users").select("id, name").eq("is_active", True).execute()
        users = users_resp.data or []
        if test_mode:
            users = users[:1]  # Only 1 user in test mode

        for user in users:
            count = await run_optimizer_for_user(user["id"])
            total_resumes += count
            logger.info(f"   {user.get('name', user['id'])}: {count} resumes generated")

        stats["resumes_generated"] = total_resumes
        logger.info(f"   ✅ Total: {total_resumes} resumes generated")
    except Exception as e:
        logger.error(f"   ❌ AI generation failed: {e}")

    # ── Step 4: Generate PDFs ───────────────────────────────────────────────────────
    logger.info("\n📄 STEP 4: PDF Generation")
    total_pdfs = 0
    try:
        for user in users:  # reuse users list from Step 3
            count = await run_pdf_generator_for_user(user["id"])
            total_pdfs += count
            if count:
                logger.info(f"   {user.get('name', user['id'])}: {count} PDF(s) generated")
        stats["pdfs_generated"] = total_pdfs
        logger.info(f"   ✅ Total: {total_pdfs} PDF(s) generated")
    except Exception as e:
        logger.error(f"   ❌ PDF generation failed: {e}")
        stats["pdfs_generated"] = 0

    # ── Step 5: Send Morning Digest ───────────────────────────────────────────
    logger.info("\n📧 STEP 5: Sending Morning Digest")
    emails_sent = 0
    if test_mode:
        logger.info("   ⏭️  Email skipped in test mode")
    else:
        try:
            for user in users:
                success = await send_morning_digest(user["id"])
                if success:
                    emails_sent += 1
            logger.info(f"   ✅ Total: {emails_sent} email(s) sent")
        except Exception as e:
            logger.error(f"   ❌ Email sending failed: {e}")
    stats["email_sent"] = emails_sent > 0

    # ── Done ──────────────────────────────────────────────────────────────────
    duration = round(time.time() - start_time, 2)
    stats["duration_seconds"] = duration
    stats["status"] = "completed"

    if run_id:
        try:
            update_payload = {
                "jobs_fetched": stats.get("jobs_fetched", 0),
                "jobs_matched": stats.get("jobs_matched", 0),
                "resumes_generated": stats.get("resumes_generated", 0),
                "duration_seconds": stats.get("duration_seconds"),
                "status": stats.get("status", "completed"),
                "step_jobs_fetched": stats.get("jobs_fetched", 0) > 0,
                "step_jobs_matched": stats.get("jobs_matched", 0) > 0,
                "step_ai_generated": stats.get("resumes_generated", 0) > 0,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            supabase.table("pipeline_status").update(update_payload).eq("id", run_id).execute()
        except Exception as e:
            logger.warning(f"Could not update pipeline_status: {e}")

    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Pipeline Complete in {duration}s")
    logger.info(f"   Jobs fetched:     {stats.get('jobs_fetched', 0)}")
    logger.info(f"   Jobs matched:     {stats.get('jobs_matched', 0)}")
    logger.info(f"   Resumes generated:{stats.get('resumes_generated', 0)}")
    logger.info(f"   PDFs generated:   {stats.get('pdfs_generated', 0)}")
    logger.info("=" * 60)

    return stats


if __name__ == "__main__":
    import os
    os.makedirs("logs", exist_ok=True)

    test_mode = "--test" in sys.argv
    asyncio.run(run_pipeline(test_mode=test_mode))
