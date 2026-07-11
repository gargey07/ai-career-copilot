"""
API Usage Guard — Daily Budget Enforcement
────────────────────────────────────────────
Stops any single external API (Adzuna, JSearch, Gemini, OpenAI, Resend...)
from being called past its free-tier or spend limit in a day. Counts are
kept in the `api_usage` Supabase table (not in memory) because the daily
pipeline runs as a fresh process each time — an in-memory counter would
reset on every run and never actually cap anything.

Usage:
    from core.usage_guard import check_budget, BudgetExceededError
    if not check_budget("adzuna", settings.adzuna_daily_limit, amount=pages):
        return []  # today's budget for this service is used up
"""
from __future__ import annotations
import logging
from datetime import date

from database.supabase_client import get_supabase

logger = logging.getLogger(__name__)


class BudgetExceededError(RuntimeError):
    """Raised when a service's daily call budget is already exhausted."""


def check_budget(service: str, daily_limit: int, amount: int = 1) -> bool:
    """
    Checks whether `service` has at least `amount` calls left in today's
    budget and, if so, consumes them. Returns True if the caller may
    proceed, False if today's budget is already used up.

    `daily_limit <= 0` disables enforcement (treated as unlimited).
    """
    if daily_limit <= 0:
        return True

    today = date.today().isoformat()
    supabase = get_supabase()

    try:
        resp = (
            supabase.table("api_usage")
            .select("count")
            .eq("service", service)
            .eq("usage_date", today)
            .execute()
        )
        current = resp.data[0]["count"] if resp.data else 0

        if current + amount > daily_limit:
            logger.warning(
                f"🚫 Daily budget exceeded for '{service}': "
                f"{current}/{daily_limit} used — skipping."
            )
            return False

        supabase.table("api_usage").upsert(
            {"service": service, "usage_date": today, "count": current + amount},
            on_conflict="service,usage_date",
        ).execute()
        return True

    except Exception as e:
        # Fail OPEN: a hiccup in usage tracking shouldn't take down the
        # whole pipeline. Worst case we occasionally under-count by a call.
        logger.warning(f"⚠️  Usage guard check failed for '{service}' ({e}) — allowing call.")
        return True


def record_usage_event(service: str, amount: int = 1) -> None:
    """
    Unconditional counter bump — no budget semantics, never blocks, never
    raises. Used for diagnostics counters like '{provider}_fail' so the
    admin usage screen can show WHY a provider is being skipped (core/ai.py
    waterfall) without anyone needing server log access.
    """
    today = date.today().isoformat()
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("api_usage")
            .select("count")
            .eq("service", service)
            .eq("usage_date", today)
            .execute()
        )
        current = resp.data[0]["count"] if resp.data else 0
        supabase.table("api_usage").upsert(
            {"service": service, "usage_date": today, "count": current + amount},
            on_conflict="service,usage_date",
        ).execute()
    except Exception as e:
        logger.debug(f"Usage event '{service}' not recorded ({e}) — diagnostics only, ignoring.")
