"""
Admin Alert System — T-013
────────────────────────────────────────────────────────────
Sends failure alert emails to the founder when the pipeline
encounters critical errors.

Triggers:
  - Pipeline fails entirely (exception in run_pipeline)
  - 0 jobs fetched after 3+ active users
  - 0 emails sent when users were due for digest
  - AI provider chain fully exhausted

Usage:
    from core.admin_alerts import alert_pipeline_failure, alert_ai_exhausted
    await alert_pipeline_failure("Step 3 crashed", stats)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── HTML email template ───────────────────────────────────────────────────────
_ALERT_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0f0f0f; color: #e0e0e0; margin: 0; padding: 20px; }}
  .card {{ background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px; max-width: 600px; margin: 0 auto; padding: 32px; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;
            background: #ff3b30; color: white; margin-bottom: 16px; }}
  h1 {{ color: #ff3b30; margin: 0 0 8px; font-size: 22px; }}
  .subtitle {{ color: #888; font-size: 14px; margin-bottom: 24px; }}
  .section {{ background: #111; border-radius: 8px; padding: 16px; margin: 16px 0; }}
  .section h3 {{ margin: 0 0 8px; font-size: 13px; color: #888; text-transform: uppercase; letter-spacing: 1px; }}
  .section p {{ margin: 0; font-size: 14px; line-height: 1.6; color: #ccc; }}
  .stat {{ display: flex; justify-content: space-between; padding: 6px 0;
           border-bottom: 1px solid #222; font-size: 13px; }}
  .stat:last-child {{ border-bottom: none; }}
  .stat .label {{ color: #888; }}
  .stat .value {{ color: #fff; font-weight: 500; }}
  .footer {{ text-align: center; color: #555; font-size: 12px; margin-top: 24px; }}
</style>
</head>
<body>
<div class="card">
  <span class="badge">🚨 PIPELINE ALERT</span>
  <h1>{title}</h1>
  <p class="subtitle">{subtitle}</p>

  <div class="section">
    <h3>Error Details</h3>
    <p style="font-family: monospace; color: #ff6b6b;">{error}</p>
  </div>

  <div class="section">
    <h3>Pipeline Stats</h3>
    {stats_html}
  </div>

  <div class="section">
    <h3>Environment</h3>
    <p>Time: {timestamp}<br>Env: {env}</p>
  </div>

  <div class="footer">
    AI Career Copilot · Admin Alert · <a href="https://supabase.com/dashboard/project/odnysgpixuhgozoczwpu" style="color: #555;">View DB</a>
  </div>
</div>
</body>
</html>
"""


def _build_stats_html(stats: dict) -> str:
    if not stats:
        return "<p>No stats available</p>"
    rows = []
    for key, val in stats.items():
        rows.append(
            f'<div class="stat"><span class="label">{key.replace("_", " ").title()}</span>'
            f'<span class="value">{val}</span></div>'
        )
    return "".join(rows)


async def _send_alert_email(subject: str, html: str) -> bool:
    """Send alert via Resend to the founder email."""
    try:
        import resend
        resend.api_key = settings.resend_api_key

        resend.Emails.send({
            "from": f"{settings.email_from_name} Alerts <{settings.email_from}>",
            "to": [settings.founder_email],
            "subject": subject,
            "html": html,
        })
        logger.info(f"📨 Admin alert sent: {subject}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send admin alert: {e}")
        return False


# ── Alert functions ───────────────────────────────────────────────────────────
async def alert_pipeline_failure(
    error: str,
    stats: dict[str, Any] = None,
    step: str = "Unknown Step",
) -> bool:
    """
    Send alert when the pipeline crashes completely.
    Call this in the top-level exception handler of run_pipeline().
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = _ALERT_HTML.format(
        title="Pipeline Failure",
        subtitle=f"Failed at: {step}",
        error=str(error)[:800],
        stats_html=_build_stats_html(stats or {}),
        timestamp=now,
        env=settings.app_env,
    )
    return await _send_alert_email(
        subject=f"🚨 [AI Copilot] Pipeline Failed — {step}",
        html=html,
    )


async def alert_zero_jobs_fetched(active_users: int, categories: list[str]) -> bool:
    """Alert when job fetching returns 0 results for active users."""
    if active_users < 1:
        return False  # No users — no alert needed

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = _ALERT_HTML.format(
        title="Zero Jobs Fetched",
        subtitle=f"{active_users} active user(s) got no jobs today",
        error=f"0 jobs fetched for categories: {', '.join(categories)}",
        stats_html=_build_stats_html({
            "active_users": active_users,
            "categories_tried": len(categories),
            "categories": ", ".join(categories),
        }),
        timestamp=now,
        env=settings.app_env,
    )
    return await _send_alert_email(
        subject="⚠️  [AI Copilot] Zero Jobs Fetched Today",
        html=html,
    )


async def alert_ai_exhausted(error: str) -> bool:
    """Alert when ALL 6 AI providers in the waterfall chain fail."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = _ALERT_HTML.format(
        title="All AI Providers Exhausted",
        subtitle="The 6-provider waterfall chain completely failed",
        error=str(error)[:800],
        stats_html=_build_stats_html({
            "providers_tried": "Groq → OpenRouter → GitHub → Gemini → Mistral → Cohere",
            "action_needed": "Check API keys and rate limits",
        }),
        timestamp=now,
        env=settings.app_env,
    )
    return await _send_alert_email(
        subject="🔥 [AI Copilot] All AI Providers Failed — Action Required",
        html=html,
    )


async def alert_email_send_failures(failed_count: int, total: int) -> bool:
    """Alert when most digest emails fail to send."""
    if failed_count == 0 or (failed_count / max(total, 1)) < 0.5:
        return False  # Less than 50% fail rate — probably fine

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = _ALERT_HTML.format(
        title="Digest Email Failures",
        subtitle=f"{failed_count}/{total} digest emails failed to send",
        error="High email failure rate — check Resend API key and quota",
        stats_html=_build_stats_html({
            "failed": failed_count,
            "total": total,
            "failure_rate": f"{failed_count/max(total,1)*100:.0f}%",
        }),
        timestamp=now,
        env=settings.app_env,
    )
    return await _send_alert_email(
        subject=f"⚠️  [AI Copilot] {failed_count}/{total} Emails Failed",
        html=html,
    )
