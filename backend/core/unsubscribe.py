"""
Unsubscribe tokens — signed, no expiry, no login required
────────────────────────────────────────────────────────
Every digest email carries a link like /unsubscribe?token=<user_id>.<sig>.
The signature is an HMAC-SHA256 over the user_id keyed with APP_SECRET_KEY,
so a token can't be forged or enumerated, but it also never expires — an
unsubscribe link must keep working for as long as the email sits in
someone's inbox (best practice / CAN-SPAM expects at minimum 30 days; we
just don't bother with an expiry at all).

Deliberately NOT a JWT/itsdangerous dependency — this is a single boolean
claim (their own user_id), so a plain HMAC is the whole solution.
"""
from __future__ import annotations
import hashlib
import hmac

from core.config import get_settings

settings = get_settings()


def generate_unsubscribe_token(user_id: str) -> str:
    sig = hmac.new(settings.app_secret_key.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{sig}"


def verify_unsubscribe_token(token: str) -> str | None:
    """Returns the user_id if the token is valid, else None."""
    try:
        user_id, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(settings.app_secret_key.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return user_id
