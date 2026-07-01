"""
Email Sender — Phase 8
────────────────────────────────────────────────────────────
Sends the Morning Digest email using the Resend API.
Fetches user's matched jobs for the day that have PDFs ready,
renders the HTML template, and emails them.
"""

import logging
from datetime import date
from typing import Optional

import resend
from jinja2 import Environment, FileSystemLoader

from core.config import get_settings
from database.supabase_client import get_supabase
from pathlib import Path

logger = logging.getLogger(__name__)
settings = get_settings()

resend.api_key = settings.resend_api_key
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _render_email_html(user_name: str, jobs: list[dict]) -> str:
    """Render the Jinja2 HTML email template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("email_digest.html")
    
    return template.render(
        user_name=user_name.split()[0] if user_name else "There",
        today=date.today().strftime("%B %d, %Y"),
        jobs=jobs
    )


async def send_morning_digest(user_id: str) -> bool:
    """
    Fetch today's pdf_ready jobs for the user and send the digest email.
    Returns True if sent successfully.
    """
    if not settings.resend_api_key:
        logger.warning("   ⚠️  RESEND_API_KEY not set — skipping email.")
        return False

    supabase = get_supabase()
    today = date.today().isoformat()

    # Fetch user data
    user_resp = supabase.table("users").select("name, email").eq("id", user_id).single().execute()
    if not user_resp.data:
        logger.error(f"   ❌ User not found: {user_id}")
        return False
    
    user = user_resp.data

    # Fetch today's pdf_ready jobs
    matches_resp = (
        supabase.table("user_jobs")
        .select("id, match_score, pdf_url, jobs(title, company, location, source_url, source, is_remote)")
        .eq("user_id", user_id)
        .eq("digest_date", today)
        .eq("status", "pdf_ready")
        .order("match_score", desc=True)
        .execute()
    )
    matches = matches_resp.data or []

    if not matches:
        logger.info(f"   No pdf_ready matches for user {user.get('email')} to email.")
        return False

    # Format job data for template
    jobs_data = []
    for m in matches:
        job = m["jobs"]
        jobs_data.append({
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "apply_url": job.get("source_url", "#"),
            "source": job.get("source", ""),
            "is_remote": job.get("is_remote", False),
            "match_score": m.get("match_score", 0.0),
            "pdf_url": m.get("pdf_url")
        })

    logger.info(f"   📧 Sending digest to {user.get('email')} with {len(jobs_data)} jobs")

    html_content = _render_email_html(user.get("name", ""), jobs_data)
    
    # Send via Resend
    # Note: On Resend free tier, you can only send to your verified domain emails, 
    # unless you add the user to your test audience or verify the domain.
    # For testing, we use the onboarding email from Resend.
    try:
        r = resend.Emails.send({
            "from": "AI Career Copilot <onboarding@resend.dev>",
            "to": [user["email"]],
            "subject": f"Your Morning Job Matches — {date.today().strftime('%b %d')}",
            "html": html_content
        })
        
        # Log success
        supabase.table("email_logs").insert({
            "user_id": user_id,
            "email_address": user["email"],
            "type": "morning_digest",
            "subject": f"Your Morning Job Matches — {date.today().strftime('%b %d')}",
            "status": "sent"
        }).execute()
        
        # Update user_jobs status to 'emailed'
        match_ids = [m["id"] for m in matches]
        supabase.table("user_jobs").update({"status": "emailed"}).in_("id", match_ids).execute()
        
        logger.info(f"   ✅ Digest emailed successfully! (ID: {r.get('id')})")
        return True
        
    except Exception as e:
        logger.error(f"   ❌ Email failed: {e}")
        supabase.table("email_logs").insert({
            "user_id": user_id,
            "email_address": user["email"],
            "type": "morning_digest",
            "subject": f"Your Morning Job Matches — {date.today().strftime('%b %d')}",
            "status": "failed",
            "error_message": str(e)
        }).execute()
        return False


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    
    import asyncio
    
    # Test with the first user
    supabase = get_supabase()
    user_res = supabase.table("users").select("id").limit(1).execute()
    if user_res.data:
        asyncio.run(send_morning_digest(user_res.data[0]["id"]))
    else:
        print("No users in DB.")
