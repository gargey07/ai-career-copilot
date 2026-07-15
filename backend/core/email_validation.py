"""
Email validation — structure + known-typo-domain detection
───────────────────────────────────────────────────────────
2026-07 production incident: a signup stored `...@gmial.com` (typo of
gmail.com). The system then faithfully mailed that address every day —
daily digest, weekly review — and every send bounced back to the sending
Gmail account's inbox, daily. Worse, Gmail SMTP accepts the message and
bounces ASYNCHRONOUSLY, so email_logs recorded status='sent' and the
admin email-history panel showed nothing wrong.

Nothing validated emails anywhere: the frontend input's type="email"
only checks shape (a typo'd domain is perfectly valid shape), and the
backend stored the raw string. This module is the shared gate.

Policy: reject-with-suggestion, never silently auto-correct — a rare
legitimate address on an unusual domain must stay possible, so only the
KNOWN-typo list blocks, and the user fixes their own input.
"""
from __future__ import annotations
import re

# High-frequency misspellings of the major mail domains -> what the user
# almost certainly meant. Keep this list to unambiguous typos only —
# anything debatable doesn't belong here (see module docstring policy).
KNOWN_TYPO_DOMAINS: dict[str, str] = {
    "gmial.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmal.com": "gmail.com",
    "gmali.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "gmail.co": "gmail.com",
    "gmail.cm": "gmail.com",
    "hotmial.com": "hotmail.com",
    "hotmal.com": "hotmail.com",
    "hotmail.co": "hotmail.com",
    "yahooo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "yahoo.co": "yahoo.com",
    "outlok.com": "outlook.com",
    "outloook.com": "outlook.com",
    "iclod.com": "icloud.com",
    "icloud.co": "icloud.com",
}

# Deliberately simple structural check — one @, non-empty local part, a
# domain containing a dot. Full RFC 5322 validation rejects real
# addresses and still can't catch the actual production failure mode
# (a well-formed address on a typo'd domain).
_EMAIL_SHAPE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def suggest_email_fix(email: str) -> str | None:
    """
    None when the address looks fine; otherwise a human-readable message
    (including a concrete suggestion for known typo domains) suitable to
    show the user verbatim.
    """
    cleaned = (email or "").strip()
    if not cleaned:
        return "Please enter your email address."
    if not _EMAIL_SHAPE_RE.match(cleaned):
        return "That doesn't look like a valid email address — please double-check it."
    local, _, domain = cleaned.rpartition("@")
    corrected = KNOWN_TYPO_DOMAINS.get(domain.lower())
    if corrected:
        return f"That email domain looks misspelled — did you mean {local}@{corrected}?"
    return None
