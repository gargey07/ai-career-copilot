"""
Dashboard access tokens — signed, no expiry, no login required
──────────────────────────────────────────────────────────────
Dashboard links carry `?t=<user_id>.<sig>` instead of a raw user_id, so a
dashboard (and its write endpoints: feedback, retry-pdf, preferences,
applied) can only be reached by someone holding a link we actually issued
— guessing another user's UUID no longer grants access to anything.

Same construction as core/unsubscribe.py, with one critical difference:
the MAC is computed over a PURPOSE-PREFIXED payload ("dash:" + user_id),
not the raw user_id. Unsubscribe tokens sign the raw user_id and sit in
the footer of every email ever sent — without domain separation here,
every one of those unsubscribe links would double as a dashboard login
token. The prefix makes the two token families mutually unusable.
(Unsubscribe keeps its raw format: links already in inboxes must keep
working, and the worst an unsubscribe token can do is unsubscribe.)

No expiry, deliberately: like unsubscribe links, dashboard links live in
email inboxes indefinitely, and this beta has no session/re-auth flow to
fall back on. Rotating APP_SECRET_KEY invalidates every issued link.
"""
from __future__ import annotations
import hashlib
import hmac

from core.config import get_settings

settings = get_settings()

_PURPOSE = b"dash:"


def generate_dashboard_token(user_id: str) -> str:
    sig = hmac.new(settings.app_secret_key.encode(), _PURPOSE + user_id.encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{sig}"


def verify_dashboard_token(token: str) -> str | None:
    """Returns the user_id if the token is valid, else None."""
    try:
        user_id, sig = token.rsplit(".", 1)
    except (ValueError, AttributeError):
        return None
    expected = hmac.new(settings.app_secret_key.encode(), _PURPOSE + user_id.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return user_id
