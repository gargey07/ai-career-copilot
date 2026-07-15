"""
Email validation — the gate behind the 2026-07 daily-bounce incident.

A signup stored `...@gmial.com` (typo of gmail.com); the app mailed it
daily and every send bounced. The founder then "fixed" their email via
the profile editor — but /resumes/confirm upserted on_conflict="email",
so the edit created a SECOND account under the corrected address and the
typo'd row lived on, still receiving (and bouncing) every daily email.

Two-part fix covered here:
1. suggest_email_fix rejects known typo domains with a suggestion.
2. /resumes/confirm accepts a dashboard_token so profile EDITS update
   the existing row by id (email changes included) instead of forking.
"""
from __future__ import annotations

from core.email_validation import suggest_email_fix


# ── The exact production address ──────────────────────────────────────────────
def test_the_actual_production_typo_is_caught_with_suggestion():
    msg = suggest_email_fix("gargeypatel123@gmial.com")
    assert msg is not None
    assert "gargeypatel123@gmail.com" in msg


def test_common_typo_domains_rejected():
    for bad in ["a@gamil.com", "a@gmal.com", "a@gmail.co", "a@hotmial.com",
                "a@yahooo.com", "a@outlok.com", "a@iclod.com"]:
        assert suggest_email_fix(bad) is not None, bad


def test_typo_detection_is_case_insensitive():
    assert suggest_email_fix("Someone@GMIAL.COM") is not None


# ── Legitimate addresses pass ──────────────────────────────────────────────────
def test_normal_addresses_pass():
    for good in ["someone@gmail.com", "a.b+tag@yahoo.com", "x@hotmail.com",
                 "dev@protonmail.com", "user@company.co.in", "n@sub.domain.org"]:
        assert suggest_email_fix(good) is None, good


def test_unusual_but_wellformed_domains_pass():
    """Policy: only the KNOWN-typo list blocks — an unfamiliar domain is
    not evidence of a typo, and silently blocking real addresses would be
    worse than the bug this prevents."""
    assert suggest_email_fix("me@gmial.io") is None  # not in the list — allowed
    assert suggest_email_fix("me@totallyrealstartup.xyz") is None


# ── Structural garbage rejected ────────────────────────────────────────────────
def test_structural_garbage_rejected():
    for bad in ["", "   ", "no-at-sign", "two@@ats.com", "no@dot", "spaces in@mail.com"]:
        assert suggest_email_fix(bad) is not None, repr(bad)


def test_whitespace_tolerated_around_valid_address():
    assert suggest_email_fix("  someone@gmail.com  ") is None


# ── Sender-level guard ─────────────────────────────────────────────────────────
def test_send_email_refuses_known_undeliverable_address(monkeypatch):
    """Last line of defense: rows that predate signup validation (or a
    ghost duplicate account) must not generate daily bounces — the sender
    itself refuses the address before any provider is attempted."""
    import asyncio
    import core.email_sender as email_sender

    def _explode(*a, **k):
        raise AssertionError("provider must never be attempted for an undeliverable address")

    monkeypatch.setattr(email_sender, "_send_via_gmail", _explode)
    monkeypatch.setattr(email_sender, "_send_via_resend", _explode)
    monkeypatch.setattr(email_sender.settings, "gmail_user", "founder@gmail.com")
    monkeypatch.setattr(email_sender.settings, "gmail_app_password", "xxxx")
    monkeypatch.setattr(email_sender.settings, "resend_api_key", "re_xxx")

    result = asyncio.run(email_sender._send_email("gargeypatel123@gmial.com", "Subject", "<p>hi</p>", ""))
    assert result is None
