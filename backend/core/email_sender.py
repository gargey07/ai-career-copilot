"""
Email Sender — Morning Digest
────────────────────────────────────────────────────────────
Sends the daily digest with the user's top matches. Provider order:

1. Gmail SMTP (GMAIL_USER + GMAIL_APP_PASSWORD) — the beta default; works
   with a plain Gmail account + app password, no domain verification.
2. Resend (RESEND_API_KEY) — used if Gmail isn't configured. Note: Resend's
   free tier only delivers to your own address until a domain is verified.

Honest by design (docs/PRODUCT_STRATEGY_BETA.md): the digest sends the top
matches we actually have — with tailored-resume links when PDFs exist, and
without them when they don't. Never blocks on a missing PDF, never sends
twice in one day, and every attempt lands in email_logs.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
import smtplib
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import httpx
from jinja2 import Environment, FileSystemLoader

from core.config import get_settings
from core.unsubscribe import generate_unsubscribe_token
from core.usage_guard import check_budget
from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)
settings = get_settings()

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
MAX_JOBS_PER_EMAIL = 5
# Tailored-resume PDFs get ATTACHED to the digest (not just linked) so the
# user can forward one straight to a recruiter. Caps keep the message well
# under provider size limits (Gmail 25MB) and download time bounded.
MAX_ATTACHMENTS_PER_EMAIL = 3
MAX_TOTAL_ATTACHMENT_BYTES = 7 * 1024 * 1024


def _render_email_html(
    user_name: str, jobs: list[dict], dashboard_url: str, unsubscribe_url: str,
    has_attachments: bool = False,
) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("email_digest.html")
    return template.render(
        user_name=user_name.split()[0] if user_name else "there",
        today=date.today().strftime("%B %d, %Y"),
        jobs=jobs,
        has_resumes=any(j.get("pdf_url") for j in jobs),
        has_attachments=has_attachments,
        dashboard_url=dashboard_url,
        unsubscribe_url=unsubscribe_url,
    )


def _safe_filename(text: str) -> str:
    """'UI/UX Designer @ Acme Pvt. Ltd' -> 'UI-UX Designer - Acme Pvt Ltd'."""
    cleaned = re.sub(r'[\\/:*?"<>|]', '-', text).strip()
    return re.sub(r'\s+', ' ', cleaned)[:80] or "resume"


async def _download_resume_attachments(jobs_data: list[dict]) -> list[tuple[str, bytes]]:
    """
    Best-effort download of tailored-resume PDFs to attach to the digest.
    Any failure just means that resume ships as a link only — never blocks
    or delays the email itself.
    """
    attachments: list[tuple[str, bytes]] = []
    total = 0
    async with httpx.AsyncClient(timeout=20) as client:
        for job in jobs_data:
            if len(attachments) >= MAX_ATTACHMENTS_PER_EMAIL:
                break
            if not job.get("pdf_url"):
                continue
            try:
                resp = await client.get(job["pdf_url"])
                resp.raise_for_status()
                content = resp.content
                if not content or total + len(content) > MAX_TOTAL_ATTACHMENT_BYTES:
                    continue
                name = _safe_filename(f"Resume - {job.get('title') or 'Role'} - {job.get('company') or ''}") + ".pdf"
                attachments.append((name, content))
                total += len(content)
            except Exception as e:
                logger.warning(f"   Couldn't attach resume PDF ({job.get('pdf_url', '')[:60]}): {e}")
    return attachments


def _build_gmail_message(
    to_email: str, subject: str, html: str, unsubscribe_url: str,
    attachments: list[tuple[str, bytes]],
) -> MIMEMultipart:
    """Pure message assembly — split out so tests can verify attachments."""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{settings.email_from_name} <{settings.gmail_user}>"
    msg["To"] = to_email
    # RFC 8058 one-click unsubscribe — recognized by Gmail/Outlook to show
    # a native "Unsubscribe" affordance next to the sender, independent of
    # the footer link. Costs nothing, meaningfully helps deliverability.
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    body = MIMEMultipart("alternative")
    body.attach(MIMEText(html, "html"))
    msg.attach(body)

    for filename, content in attachments:
        part = MIMEApplication(content, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
    return msg


def _send_via_gmail(
    to_email: str, subject: str, html: str, unsubscribe_url: str,
    attachments: list[tuple[str, bytes]],
) -> None:
    """Blocking SMTP send — call through asyncio.to_thread."""
    msg = _build_gmail_message(to_email, subject, html, unsubscribe_url, attachments)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(settings.gmail_user, settings.gmail_app_password)
        server.sendmail(settings.gmail_user, [to_email], msg.as_string())


def _send_via_resend(
    to_email: str, subject: str, html: str, unsubscribe_url: str,
    attachments: list[tuple[str, bytes]],
) -> None:
    import resend

    resend.api_key = settings.resend_api_key
    payload = {
        "from": f"{settings.email_from_name} <onboarding@resend.dev>",
        "to": [to_email],
        "subject": subject,
        "html": html,
        "headers": {
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }
    if attachments:
        payload["attachments"] = [
            {"filename": name, "content": base64.b64encode(content).decode()}
            for name, content in attachments
        ]
    resend.Emails.send(payload)


async def _send_email(
    to_email: str, subject: str, html: str, unsubscribe_url: str,
    attachments: list[tuple[str, bytes]] | None = None,
) -> str | None:
    """
    Send through the first configured provider (within budget).
    Returns the provider name used, or None if nothing is configured/available.
    """
    attachments = attachments or []
    if settings.gmail_user and settings.gmail_app_password:
        if not check_budget("gmail", settings.gmail_daily_limit):
            return None
        await asyncio.to_thread(_send_via_gmail, to_email, subject, html, unsubscribe_url, attachments)
        return "gmail"

    if settings.resend_api_key:
        if not check_budget("resend", settings.resend_daily_limit):
            return None
        await asyncio.to_thread(_send_via_resend, to_email, subject, html, unsubscribe_url, attachments)
        return "resend"

    logger.info("   No email provider configured (set GMAIL_USER + GMAIL_APP_PASSWORD, or RESEND_API_KEY) — skipping email.")
    return None


def _already_sent_today(supabase, user_id: str) -> bool:
    """Idempotency: manual pipeline re-runs must not double-send a digest."""
    try:
        resp = (
            supabase.table("email_logs")
            .select("id")
            .eq("user_id", user_id)
            .eq("type", "morning_digest")
            .eq("status", "sent")
            .gte("sent_at", date.today().isoformat())
            .limit(1)
            .execute()
        )
        return bool(resp.data)
    except Exception:
        # If the log check itself fails, err on the side of not spamming.
        logger.warning("   Couldn't check email_logs — skipping send to avoid duplicates.")
        return True


async def send_morning_digest(user_id: str) -> bool:
    """
    Email the user their top matches for today. Includes tailored-resume
    links for matches that have PDFs; still sends without them. Returns
    True if an email went out.
    """
    supabase = get_supabase()
    today = date.today().isoformat()

    try:
        user_resp = supabase.table("users").select("name, email, is_subscribed").eq("id", user_id).single().execute()
    except Exception:
        # is_subscribed is a newer column — don't let a missing migration
        # break the digest send (defaults to subscribed below).
        user_resp = supabase.table("users").select("name, email").eq("id", user_id).single().execute()
    if not user_resp.data or not user_resp.data.get("email"):
        logger.error(f"   ❌ User not found or has no email: {user_id}")
        return False
    user = user_resp.data

    # is_subscribed gates EMAIL only — unsubscribing must never silently
    # stop matching/dashboard updates (docs/PRODUCT_STRATEGY_BETA.md).
    # Defaults to subscribed if the column is missing (pre-migration DB).
    if user.get("is_subscribed") is False:
        logger.info(f"   {user['email']} is unsubscribed — skipping digest.")
        return False

    if _already_sent_today(supabase, user_id):
        logger.info(f"   Digest already sent today to {user['email']} — skipping.")
        return False

    matches_resp = (
        supabase.table("user_jobs")
        .select("id, match_score, pdf_url, status, jobs(title, company, location, source_url, source, is_remote)")
        .eq("user_id", user_id)
        .eq("digest_date", today)
        .order("match_score", desc=True)
        .limit(MAX_JOBS_PER_EMAIL)
        .execute()
    )
    matches = matches_resp.data or []
    if not matches:
        logger.info(f"   No matches today for {user['email']} — nothing to email.")
        return False

    backend = settings.backend_url.rstrip("/")

    def _normalized_score(raw) -> float:
        # Stored scores exist in two scales: 0–1 (original matcher) and
        # 0–100 (the replaced match_jobs SQL function) — same fix as the
        # dashboard, or the email prints things like "7930% match".
        score = raw or 0.0
        return min(score / 100.0, 1.0) if score > 1 else score

    jobs_data = [
        {
            "title": (m.get("jobs") or {}).get("title"),
            "company": (m.get("jobs") or {}).get("company"),
            "location": (m.get("jobs") or {}).get("location"),
            "apply_url": (m.get("jobs") or {}).get("source_url", "#"),
            # Routed through the click-tracking redirect (docs/PRODUCT_STRATEGY_BETA.md
            # "Apply link click rate" metric) rather than linking straight to the board.
            "apply_redirect_url": f"{backend}/r/{m['id']}",
            "is_remote": (m.get("jobs") or {}).get("is_remote", False),
            "match_score": _normalized_score(m.get("match_score")),
            "pdf_url": m.get("pdf_url"),
        }
        for m in matches
    ]

    # Attach the tailored-resume PDFs themselves (best-effort) so the user
    # can forward the email straight to a recruiter without clicking out.
    attachments = await _download_resume_attachments(jobs_data)

    frontend = (settings.frontend_url or "https://ai-career-copilot-taupe-five.vercel.app").rstrip("/")
    dashboard_url = f"{frontend}/dashboard?user_id={user_id}"
    unsubscribe_url = f"{backend}/unsubscribe?token={generate_unsubscribe_token(user_id)}"
    subject = f"Your top {len(jobs_data)} job match{'es' if len(jobs_data) != 1 else ''} — {date.today().strftime('%b %d')}"
    html = _render_email_html(
        user.get("name", ""), jobs_data, dashboard_url, unsubscribe_url,
        has_attachments=bool(attachments),
    )

    log_row = {
        "user_id": user_id,
        "email_address": user["email"],
        "type": "morning_digest",
        "subject": subject,
    }
    try:
        provider = await _send_email(user["email"], subject, html, unsubscribe_url, attachments)
        if provider is None:
            return False

        supabase.table("email_logs").insert({**log_row, "status": "sent"}).execute()
        match_ids = [m["id"] for m in matches]
        supabase.table("user_jobs").update({"status": "emailed"}).in_("id", match_ids).execute()
        logger.info(f"   ✅ Digest sent to {user['email']} via {provider} ({len(jobs_data)} jobs)")
        return True

    except Exception as e:
        logger.error(f"   ❌ Email failed for {user['email']}: {e}")
        try:
            supabase.table("email_logs").insert({**log_row, "status": "failed", "error_message": str(e)}).execute()
        except Exception:
            pass
        return False


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    supabase = get_supabase()
    user_res = supabase.table("users").select("id").limit(1).execute()
    if user_res.data:
        asyncio.run(send_morning_digest(user_res.data[0]["id"]))
    else:
        print("No users in DB.")
