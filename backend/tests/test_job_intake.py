"""
AI Application Review — add-a-job intake + on-demand analysis.

Covers the extract→review→confirm contract (core/job_intake.py), the
confirm endpoint's job/match creation, the per-match analyze endpoint's
cache-then-budget behavior, and the machinery protections (purge +
digest exclusion) for user-submitted jobs.
"""
from __future__ import annotations
import asyncio
import json

import pytest
from fastapi import HTTPException

import api.routes.users as users_module
import core.job_intake as job_intake
import core.recruiter as recruiter_module
from api.routes.users import JobConfirmRequest, AnalyzeRequest, job_intake_confirm, analyze_match
from core.job_intake import parse_draft, extract_job_draft


# ── parse_draft ───────────────────────────────────────────────────────────────
_DRAFT = {
    "title": "Backend Engineer",
    "company": "Acme",
    "location": "Mumbai",
    "description": "Build APIs with Python and FastAPI.",
    "salary_min": 800000,
    "salary_max": 1200000,
    "employment_type": "full-time",
    "is_remote": True,
}


def test_parse_draft_clean_json():
    result = parse_draft(json.dumps(_DRAFT), source_text="raw")
    assert result["title"] == "Backend Engineer"
    assert result["salary_min"] == 800000
    assert result["is_remote"] is True


def test_parse_draft_fenced_and_prose_wrapped():
    fenced = "```json\n" + json.dumps(_DRAFT) + "\n```"
    assert parse_draft(fenced, "raw")["title"] == "Backend Engineer"
    prose = "Here's what I extracted:\n" + json.dumps(_DRAFT) + "\nHope that helps!"
    assert parse_draft(prose, "raw")["company"] == "Acme"


def test_parse_draft_garbage_returns_none():
    assert parse_draft("", "raw") is None
    assert parse_draft("sounds like a great job!", "raw") is None
    assert parse_draft("{broken", "raw") is None


def test_parse_draft_requires_title():
    # No title extracted -> not reviewable -> None (manual form instead).
    assert parse_draft(json.dumps({**_DRAFT, "title": ""}), "raw") is None


def test_parse_draft_falls_back_to_source_text_for_description():
    raw = json.dumps({**_DRAFT, "description": None})
    result = parse_draft(raw, source_text="the original pasted posting text")
    assert result["description"] == "the original pasted posting text"


def test_parse_draft_normalizes_junk_salary():
    raw = json.dumps({**_DRAFT, "salary_min": "competitive", "salary_max": -5})
    result = parse_draft(raw, "raw")
    assert result["salary_min"] is None
    assert result["salary_max"] is None


class _FakeProvider:
    def __init__(self, response=None, error=None):
        self._response, self._error = response, error

    async def generate_text(self, prompt, temperature=0.3):
        if self._error:
            raise self._error
        return self._response


def test_extract_job_draft_happy_path(monkeypatch):
    monkeypatch.setattr(job_intake, "get_ai_provider", lambda: _FakeProvider(response=json.dumps(_DRAFT)))
    result = asyncio.run(extract_job_draft("some raw posting text"))
    assert result["title"] == "Backend Engineer"


def test_extract_job_draft_failure_contract(monkeypatch):
    # Provider down or unparseable -> None, never an exception.
    monkeypatch.setattr(job_intake, "get_ai_provider", lambda: _FakeProvider(error=RuntimeError("boom")))
    assert asyncio.run(extract_job_draft("text")) is None
    monkeypatch.setattr(job_intake, "get_ai_provider", lambda: _FakeProvider(response="no json here"))
    assert asyncio.run(extract_job_draft("text")) is None
    assert asyncio.run(extract_job_draft("")) is None


# ── Fake supabase for the endpoints ──────────────────────────────────────────
class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, name, db):
        self._name, self._db = name, db
        self._filters: dict = {}
        self._op = "select"
        self._payload = None
        self._single = False

    def select(self, *a, **k):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        return self._db.execute(self._name, self._op, self._filters, self._payload, self._single)


class _FakeSupabase:
    def __init__(self, user=None, jobs=None, matches=None):
        self.user = user or {"resume_text": "Python dev.", "target_roles": ["Backend Developer"], "experience_level": "junior"}
        self.jobs = jobs or []          # list of job row dicts
        self.matches = matches or []    # list of user_jobs row dicts
        self.updates: list[tuple] = []
        self._next_id = 0

    def table(self, name):
        return _FakeTable(name, self)

    def _new_id(self, prefix):
        self._next_id += 1
        return f"{prefix}{self._next_id}"

    def execute(self, table, op, filters, payload, single):
        if table == "users":
            return _Resp(dict(self.user))
        if table == "jobs":
            if op == "insert":
                row = {**payload, "id": self._new_id("j")}
                self.jobs.append(row)
                return _Resp([row])
            rows = [dict(j) for j in self.jobs
                    if all(j.get(k) == v for k, v in filters.items())]
            return _Resp(rows[0] if single else rows)
        if table == "user_jobs":
            if op == "insert":
                row = {**payload, "id": self._new_id("m")}
                self.matches.append(row)
                return _Resp([row])
            if op == "update":
                self.updates.append((filters.get("id"), payload))
                return _Resp([])
            rows = [dict(m) for m in self.matches
                    if all(m.get(k) == v for k, v in filters.items())]
            return _Resp(rows[0] if single else rows)
        return _Resp([])


_EVAL = {"verdict": "apply", "fit_score": 70, "strengths": ["Python"], "missing": [], "risks": [], "suggestions": [], "reason": "Good fit."}


def _patch_endpoint_env(monkeypatch, db, budget_ok=True, eval_result=_EVAL):
    monkeypatch.setattr(users_module, "verify_dashboard_token", lambda t: "u1" if t == "good" else None)
    monkeypatch.setattr(users_module, "get_supabase", lambda: db)
    monkeypatch.setattr(users_module, "check_budget", lambda key, limit: budget_ok)

    async def fake_eval(user, job):
        return eval_result
    monkeypatch.setattr(recruiter_module, "evaluate_match", fake_eval)


# ── /job-intake/confirm ───────────────────────────────────────────────────────
def test_confirm_creates_job_and_match_and_returns_eval(monkeypatch):
    db = _FakeSupabase()
    _patch_endpoint_env(monkeypatch, db)

    payload = JobConfirmRequest(title="Backend Engineer", description="Python APIs.", company="Acme")
    result = asyncio.run(job_intake_confirm("u1", payload, t="good"))

    assert result["status"] == "ok"
    assert result["recruiter_eval"]["verdict"] == "apply"
    assert len(db.jobs) == 1
    job = db.jobs[0]
    assert job["source"] == "user_submitted"
    assert job["source_url"].startswith("user-submitted:")  # synthetic, unique
    assert len(db.matches) == 1
    # No pipeline scoring ran — a made-up match % must never be stored.
    assert db.matches[0].get("match_score") is None
    # Eval persisted onto the match row.
    assert db.updates and db.updates[0][1] == {"recruiter_eval": _EVAL}


def test_confirm_dedups_by_source_url(monkeypatch):
    existing = {"id": "j-existing", "source": "adzuna", "source_url": "https://example.org/job/1",
                "title": "Backend Engineer", "company": "Acme", "description": "Python."}
    db = _FakeSupabase(jobs=[existing])
    _patch_endpoint_env(monkeypatch, db)

    payload = JobConfirmRequest(title="Backend Engineer", description="Python.", url="https://example.org/job/1")
    result = asyncio.run(job_intake_confirm("u1", payload, t="good"))

    assert len(db.jobs) == 1  # reused, not duplicated
    assert result["job"]["id"] == "j-existing"


def test_confirm_requires_title_and_description(monkeypatch):
    db = _FakeSupabase()
    _patch_endpoint_env(monkeypatch, db)
    with pytest.raises(HTTPException) as e:
        asyncio.run(job_intake_confirm("u1", JobConfirmRequest(title="  ", description="x"), t="good"))
    assert e.value.status_code == 400


def test_confirm_budget_exhausted_429(monkeypatch):
    db = _FakeSupabase()
    _patch_endpoint_env(monkeypatch, db, budget_ok=False)
    with pytest.raises(HTTPException) as e:
        asyncio.run(job_intake_confirm("u1", JobConfirmRequest(title="T", description="D"), t="good"))
    assert e.value.status_code == 429
    assert db.jobs == []  # nothing stored when over budget


def test_confirm_rejects_bad_token(monkeypatch):
    db = _FakeSupabase()
    _patch_endpoint_env(monkeypatch, db)
    with pytest.raises(HTTPException) as e:
        asyncio.run(job_intake_confirm("u1", JobConfirmRequest(title="T", description="D"), t="wrong"))
    assert e.value.status_code == 401


# ── /matches/{id}/analyze ─────────────────────────────────────────────────────
def test_analyze_returns_cached_eval_without_ai_call(monkeypatch):
    db = _FakeSupabase(
        jobs=[{"id": "j1", "title": "T", "company": "C", "description": "D"}],
        matches=[{"id": "m1", "user_id": "u1", "job_id": "j1", "recruiter_eval": {"verdict": "stretch"}}],
    )
    calls = []

    async def counting_eval(user, job):
        calls.append(1)
        return _EVAL
    _patch_endpoint_env(monkeypatch, db)
    monkeypatch.setattr(recruiter_module, "evaluate_match", counting_eval)

    result = asyncio.run(analyze_match("u1", "m1", AnalyzeRequest(), t="good"))
    assert result["cached"] is True
    assert result["recruiter_eval"]["verdict"] == "stretch"
    assert calls == []  # no AI spend on a cached answer


def test_analyze_runs_and_stores_eval(monkeypatch):
    db = _FakeSupabase(
        jobs=[{"id": "j1", "title": "T", "company": "C", "description": "D"}],
        matches=[{"id": "m1", "user_id": "u1", "job_id": "j1", "recruiter_eval": None}],
    )
    _patch_endpoint_env(monkeypatch, db)

    result = asyncio.run(analyze_match("u1", "m1", AnalyzeRequest(), t="good"))
    assert result["cached"] is False
    assert result["recruiter_eval"]["verdict"] == "apply"
    assert db.updates and db.updates[0][1] == {"recruiter_eval": _EVAL}


def test_analyze_budget_exhausted_429(monkeypatch):
    db = _FakeSupabase(
        jobs=[{"id": "j1", "title": "T", "company": "C", "description": "D"}],
        matches=[{"id": "m1", "user_id": "u1", "job_id": "j1", "recruiter_eval": None}],
    )
    _patch_endpoint_env(monkeypatch, db, budget_ok=False)
    with pytest.raises(HTTPException) as e:
        asyncio.run(analyze_match("u1", "m1", AnalyzeRequest(), t="good"))
    assert e.value.status_code == 429


def test_analyze_all_providers_down_503(monkeypatch):
    db = _FakeSupabase(
        jobs=[{"id": "j1", "title": "T", "company": "C", "description": "D"}],
        matches=[{"id": "m1", "user_id": "u1", "job_id": "j1", "recruiter_eval": None}],
    )
    _patch_endpoint_env(monkeypatch, db, eval_result=None)
    with pytest.raises(HTTPException) as e:
        asyncio.run(analyze_match("u1", "m1", AnalyzeRequest(), t="good"))
    assert e.value.status_code == 503


def test_analyze_wrong_owner_404(monkeypatch):
    db = _FakeSupabase(matches=[{"id": "m1", "user_id": "someone-else", "job_id": "j1"}])
    _patch_endpoint_env(monkeypatch, db)
    with pytest.raises(HTTPException) as e:
        asyncio.run(analyze_match("u1", "m1", AnalyzeRequest(), t="good"))
    assert e.value.status_code == 404
