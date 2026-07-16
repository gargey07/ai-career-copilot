"""
Fit Check round — save-for-later, decision notes, cover-letter edits.

Small per-match write endpoints (users.py); shared concerns are ownership
(404 on someone else's match), token auth, and length caps.
"""
from __future__ import annotations
import asyncio

import pytest
from fastapi import HTTPException

import api.routes.users as users_module
from api.routes.users import (
    CoverLetterEditRequest,
    NotesRequest,
    SaveRequest,
    edit_cover_letter,
    save_match,
    update_notes,
)


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeSupabase:
    """Owns one match row ('m1' belonging to 'u1'); records updates."""

    def __init__(self, fail_updates=False):
        self.updates: list[dict] = []
        self._fail_updates = fail_updates
        self._op = "select"
        self._filters: dict = {}
        self._payload = None

    def table(self, name):
        self._filters = {}
        return self

    def select(self, *a, **k):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        if self._op == "update":
            if self._fail_updates:
                raise RuntimeError("column does not exist")
            self.updates.append(dict(self._payload))
            return _Resp([])
        owned = self._filters.get("id") == "m1" and self._filters.get("user_id", "u1") == "u1"
        return _Resp([{"id": "m1"}] if owned else [])


def _patch(monkeypatch, db):
    monkeypatch.setattr(users_module, "verify_dashboard_token", lambda t: "u1" if t == "good" else None)
    monkeypatch.setattr(users_module, "get_supabase", lambda: db)


# ── save ──────────────────────────────────────────────────────────────────────
def test_save_sets_and_clears_saved_at(monkeypatch):
    db = _FakeSupabase()
    _patch(monkeypatch, db)

    result = asyncio.run(save_match("u1", "m1", SaveRequest(saved=True), t="good"))
    assert result == {"status": "ok", "saved": True}
    assert db.updates[0]["saved_at"] is not None

    result = asyncio.run(save_match("u1", "m1", SaveRequest(saved=False), t="good"))
    assert result == {"status": "ok", "saved": False}
    assert db.updates[1] == {"saved_at": None}


def test_save_wrong_owner_404(monkeypatch):
    db = _FakeSupabase()
    _patch(monkeypatch, db)
    with pytest.raises(HTTPException) as e:
        asyncio.run(save_match("u1", "someone-elses-match", SaveRequest(), t="good"))
    assert e.value.status_code == 404


def test_save_unmigrated_column_friendly_500(monkeypatch):
    db = _FakeSupabase(fail_updates=True)
    _patch(monkeypatch, db)
    with pytest.raises(HTTPException) as e:
        asyncio.run(save_match("u1", "m1", SaveRequest(), t="good"))
    assert e.value.status_code == 500


# ── notes ─────────────────────────────────────────────────────────────────────
def test_notes_persist_and_clear(monkeypatch):
    db = _FakeSupabase()
    _patch(monkeypatch, db)

    result = asyncio.run(update_notes("u1", "m1", NotesRequest(text="  recruiter messaged me  "), t="good"))
    assert result["notes"] == "recruiter messaged me"
    assert db.updates[0] == {"user_notes": "recruiter messaged me"}

    result = asyncio.run(update_notes("u1", "m1", NotesRequest(text="   "), t="good"))
    assert result["notes"] is None
    assert db.updates[1] == {"user_notes": None}


def test_notes_capped_at_limit(monkeypatch):
    db = _FakeSupabase()
    _patch(monkeypatch, db)
    result = asyncio.run(update_notes("u1", "m1", NotesRequest(text="x" * 5000), t="good"))
    assert len(result["notes"]) == 2000


def test_notes_wrong_token_401(monkeypatch):
    db = _FakeSupabase()
    _patch(monkeypatch, db)
    with pytest.raises(HTTPException) as e:
        asyncio.run(update_notes("u1", "m1", NotesRequest(text="hi"), t="bad"))
    assert e.value.status_code == 401


# ── cover-letter edits ────────────────────────────────────────────────────────
def test_cover_letter_edit_persists(monkeypatch):
    db = _FakeSupabase()
    _patch(monkeypatch, db)
    result = asyncio.run(edit_cover_letter("u1", "m1", CoverLetterEditRequest(text="Dear team, …"), t="good"))
    assert result == {"status": "ok"}
    assert db.updates[0] == {"cover_letter_text": "Dear team, …"}


def test_cover_letter_edit_rejects_empty(monkeypatch):
    db = _FakeSupabase()
    _patch(monkeypatch, db)
    with pytest.raises(HTTPException) as e:
        asyncio.run(edit_cover_letter("u1", "m1", CoverLetterEditRequest(text="   "), t="good"))
    assert e.value.status_code == 400
    assert db.updates == []


def test_cover_letter_edit_caps_length(monkeypatch):
    db = _FakeSupabase()
    _patch(monkeypatch, db)
    asyncio.run(edit_cover_letter("u1", "m1", CoverLetterEditRequest(text="y" * 20_000), t="good"))
    assert len(db.updates[0]["cover_letter_text"]) == 10_000


def test_cover_letter_edit_wrong_owner_404(monkeypatch):
    db = _FakeSupabase()
    _patch(monkeypatch, db)
    with pytest.raises(HTTPException) as e:
        asyncio.run(edit_cover_letter("u1", "not-mine", CoverLetterEditRequest(text="hi"), t="good"))
    assert e.value.status_code == 404
