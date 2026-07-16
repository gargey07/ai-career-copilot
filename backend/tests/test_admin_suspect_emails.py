"""
GET /api/admin/suspect-emails — the definitive, standalone scan.

Exists because the admin overview screen showed no red flag for a known-
bad stored email and no ghost row was visible in the (possibly stale/
not-yet-deployed) users table — this endpoint is a direct, unambiguous
answer that doesn't depend on the big /overview payload or any client
caching: query every user row fresh, run the same validator, return
exactly what's flagged right now.
"""
from __future__ import annotations
import asyncio

import api.routes.admin as admin_module
from api.routes.admin import suspect_emails


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *a, **k):
        return self

    def execute(self):
        return _Resp(self._rows)


class _FakeSupabase:
    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        assert name == "users"
        return _FakeQuery(self._rows)


def _rows():
    return [
        {"id": "u1", "name": "Gargey Patel", "email": "gargeypatel123@gmail.com", "is_active": True, "created_at": "2026-07-01"},
        {"id": "u2", "name": "Ghost", "email": "gargeypatel123@gmial.com", "is_active": True, "created_at": "2026-06-30"},
        {"id": "u3", "name": "Kevin", "email": "kevin@yahoo.com", "is_active": True, "created_at": "2026-07-10"},
    ]


def _run(db, token="secret"):
    return asyncio.run(suspect_emails(token=token))


def test_scan_flags_only_the_bad_row(monkeypatch):
    db = _FakeSupabase(_rows())
    monkeypatch.setattr(admin_module, "get_supabase", lambda: db)
    monkeypatch.setattr(admin_module.settings, "admin_token", "secret")

    result = _run(db)
    assert result["scanned"] == 3
    assert len(result["flagged"]) == 1
    flagged = result["flagged"][0]
    assert flagged["user_id"] == "u2"
    assert flagged["email"] == "gargeypatel123@gmial.com"
    assert "gargeypatel123@gmail.com" in flagged["problem"]


def test_scan_empty_when_nothing_bad(monkeypatch):
    db = _FakeSupabase([r for r in _rows() if r["id"] != "u2"])
    monkeypatch.setattr(admin_module, "get_supabase", lambda: db)
    monkeypatch.setattr(admin_module.settings, "admin_token", "secret")

    result = _run(db)
    assert result["scanned"] == 2
    assert result["flagged"] == []


def test_scan_requires_valid_admin_token(monkeypatch):
    from fastapi import HTTPException

    db = _FakeSupabase(_rows())
    monkeypatch.setattr(admin_module, "get_supabase", lambda: db)
    monkeypatch.setattr(admin_module.settings, "admin_token", "secret")

    try:
        _run(db, token="wrong-token")
        assert False, "expected HTTPException for a bad admin token"
    except HTTPException as e:
        assert e.status_code == 403
