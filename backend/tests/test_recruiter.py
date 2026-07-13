"""
AI Recruiter Evaluation — parsing, failure contract, and the optimizer gate.

Run from the repo root or backend/:
    python -m pytest backend/tests/test_recruiter.py -q
"""
from __future__ import annotations
import asyncio
import json

import core.optimizer as optimizer
import core.recruiter as recruiter
from core.recruiter import parse_eval


# ── parse_eval ────────────────────────────────────────────────────────────────
_GOOD = {
    "verdict": "apply",
    "fit_score": 82,
    "strengths": ["FastAPI", "PostgreSQL"],
    "missing": ["AWS"],
    "risks": ["No production ML experience"],
    "reason": "Strong backend overlap with the core requirements.",
}


def test_parse_clean_json():
    result = parse_eval(json.dumps(_GOOD))
    assert result["verdict"] == "apply"
    assert result["fit_score"] == 82
    assert result["strengths"] == ["FastAPI", "PostgreSQL"]
    assert result["missing"] == ["AWS"]
    assert result["reason"].startswith("Strong backend")


def test_parse_fenced_json():
    raw = "```json\n" + json.dumps(_GOOD) + "\n```"
    assert parse_eval(raw)["verdict"] == "apply"


def test_parse_prose_wrapped_json():
    raw = "Here is my evaluation:\n" + json.dumps(_GOOD) + "\nLet me know if you need more."
    assert parse_eval(raw)["verdict"] == "apply"


def test_parse_garbage_returns_none():
    assert parse_eval("I would recommend applying to this job.") is None
    assert parse_eval("") is None
    assert parse_eval("{broken json") is None


def test_parse_invalid_verdict_returns_none():
    # A gate must never act on a verdict outside the contract.
    assert parse_eval(json.dumps({**_GOOD, "verdict": "maybe"})) is None
    assert parse_eval(json.dumps({**_GOOD, "verdict": None})) is None


def test_parse_normalizes_junk_fields():
    raw = json.dumps({
        "verdict": "STRETCH",           # case-insensitive
        "fit_score": "not a number",    # -> None, never a crash
        "strengths": "FastAPI",         # non-list -> []
        "missing": [1, "  AWS  ", ""],  # coerced, stripped, empties dropped
        "reason": 42,
    })
    result = parse_eval(raw)
    assert result["verdict"] == "stretch"
    assert result["fit_score"] is None
    assert result["strengths"] == []
    assert result["missing"] == ["1", "AWS"]
    assert result["reason"] == "42"


def test_parse_clamps_fit_score():
    assert parse_eval(json.dumps({**_GOOD, "fit_score": 250}))["fit_score"] == 100
    assert parse_eval(json.dumps({**_GOOD, "fit_score": -5}))["fit_score"] == 0


# ── evaluate_match failure contract ───────────────────────────────────────────
_USER = {"resume_text": "Python developer, 3 years FastAPI.", "target_roles": ["Backend Developer"], "experience_level": "junior"}
_JOB = {"title": "Backend Engineer", "company": "Acme", "description": "Build APIs with Python and FastAPI."}


class _FakeProvider:
    def __init__(self, response=None, error=None):
        self._response, self._error = response, error
        self.calls = 0

    async def generate_text(self, prompt, temperature=0.3):
        self.calls += 1
        if self._error:
            raise self._error
        return self._response


def test_evaluate_match_happy_path(monkeypatch):
    provider = _FakeProvider(response=json.dumps(_GOOD))
    monkeypatch.setattr(recruiter, "get_ai_provider", lambda: provider)
    result = asyncio.run(recruiter.evaluate_match(_USER, _JOB))
    assert result["verdict"] == "apply"
    assert provider.calls == 1


def test_evaluate_match_provider_error_returns_none(monkeypatch):
    # Budget exhausted / provider down -> no gate, never an exception.
    monkeypatch.setattr(recruiter, "get_ai_provider", lambda: _FakeProvider(error=RuntimeError("boom")))
    assert asyncio.run(recruiter.evaluate_match(_USER, _JOB)) is None


def test_evaluate_match_unparseable_returns_none(monkeypatch):
    monkeypatch.setattr(recruiter, "get_ai_provider", lambda: _FakeProvider(response="sure, sounds good!"))
    assert asyncio.run(recruiter.evaluate_match(_USER, _JOB)) is None


def test_evaluate_match_skips_when_nothing_to_judge(monkeypatch):
    provider = _FakeProvider(response=json.dumps(_GOOD))
    monkeypatch.setattr(recruiter, "get_ai_provider", lambda: provider)
    assert asyncio.run(recruiter.evaluate_match({**_USER, "resume_text": ""}, _JOB)) is None
    assert asyncio.run(recruiter.evaluate_match(_USER, {**_JOB, "description": ""})) is None
    assert provider.calls == 0  # no AI spend on empty inputs


# ── Optimizer gate ────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    """Just enough of the supabase query-builder chain for optimizer paths."""

    def __init__(self, name, db):
        self._name, self._db = name, db
        self._filters: dict = {}
        self._op = "select"
        self._payload = None
        self._single = False

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

    def single(self):
        self._single = True
        return self

    def __getattr__(self, name):
        # neq / gte / in_ / is_ / order / limit / not_ — chain no-ops.
        def _chain(*a, **k):
            return self
        return _chain

    def execute(self):
        if self._op == "update":
            self._db.updates.append((self._name, self._filters.get("id"), self._payload))
            return _Resp([])
        return _Resp(self._db.select_response(self._name, self._filters, self._single))


class _FakeSupabase:
    def __init__(self, user, matches, jobs_by_id):
        self.user, self.matches, self.jobs_by_id = user, matches, jobs_by_id
        self.updates: list[tuple] = []  # (table, row_id, payload)

    def table(self, name):
        return _FakeTable(name, self)

    def select_response(self, table, filters, single):
        if table == "users":
            return dict(self.user)
        if table == "jobs":
            job = self.jobs_by_id.get(filters.get("id"))
            return dict(job) if job else None
        if table == "user_jobs":
            if single:
                match = next((m for m in self.matches if m["id"] == filters.get("id")), None)
                return dict(match) if match else None
            return [dict(m) for m in self.matches]
        return []

    def resume_updates(self):
        return [(rid, p) for t, rid, p in self.updates if p and "optimized_resume_text" in p]

    def eval_updates(self):
        return [(rid, p) for t, rid, p in self.updates if p and set(p) == {"recruiter_eval"}]


def _pipeline_db(quota=2):
    user = {
        "name": "Kevin", "resume_text": "Python developer.", "skills": [], "tools": [],
        "job_category": "backend_developer", "target_roles": ["Backend Developer"],
        "experience_level": "junior", "resume_quota_override": quota,
    }
    matches = [{"id": f"m{i}", "job_id": f"j{i}", "rank": i} for i in range(1, 5)]
    jobs = {
        "j1": {"title": "Product Designer", "company": "DesignCo", "description": "Figma, UX research."},
        "j2": {"title": "Backend Engineer", "company": "Acme", "description": "Python APIs."},
        "j3": {"title": "Python Developer", "company": "Beta", "description": "FastAPI services."},
        "j4": {"title": "Django Developer", "company": "Gamma", "description": "Django, DRF."},
    }
    return _FakeSupabase(user, matches, jobs)


def _patch_optimizer(monkeypatch, db, verdicts: dict | None):
    """verdicts: job title -> verdict; None means eval is unavailable."""
    monkeypatch.setattr(optimizer, "get_supabase", lambda: db)
    monkeypatch.setattr(optimizer, "_find_recent_resume", lambda *a, **k: None)

    async def fake_eval(user, job):
        if verdicts is None:
            return None
        verdict = verdicts.get(job["title"], "apply")
        return {"verdict": verdict, "fit_score": 50, "strengths": [], "missing": [], "risks": [], "reason": "test"}
    monkeypatch.setattr(optimizer, "evaluate_match", fake_eval)

    async def fake_optimize(**kwargs):
        return "TAILORED RESUME"
    monkeypatch.setattr(optimizer, "optimize_resume", fake_optimize)


def test_gate_skip_frees_slot_for_next_ranked(monkeypatch):
    db = _pipeline_db(quota=2)
    _patch_optimizer(monkeypatch, db, verdicts={"Product Designer": "skip"})

    generated = asyncio.run(optimizer.run_optimizer_for_user("u1"))

    assert generated == 2
    # j1 (wrong profession) vetoed; slots went to j2 and j3; j4 never reached.
    assert [rid for rid, _ in db.resume_updates()] == ["m2", "m3"]
    # Eval stored for the vetoed match AND the generated ones — the
    # dashboard shows WHY in every case.
    assert {rid for rid, _ in db.eval_updates()} == {"m1", "m2", "m3"}
    assert db.eval_updates()[0][1]["recruiter_eval"]["verdict"] == "skip"


def test_gate_absent_when_eval_unavailable(monkeypatch):
    # AI hiccup -> no gate, resumes still generate for the top-ranked jobs.
    db = _pipeline_db(quota=2)
    _patch_optimizer(monkeypatch, db, verdicts=None)

    generated = asyncio.run(optimizer.run_optimizer_for_user("u1"))

    assert generated == 2
    assert [rid for rid, _ in db.resume_updates()] == ["m1", "m2"]
    assert db.eval_updates() == []


def test_gate_stops_at_quota_even_with_spares(monkeypatch):
    db = _pipeline_db(quota=2)
    _patch_optimizer(monkeypatch, db, verdicts={})  # everything "apply"

    generated = asyncio.run(optimizer.run_optimizer_for_user("u1"))

    assert generated == 2
    # Only the winning candidates cost eval calls — spares beyond the
    # quota are never evaluated (budget discipline).
    assert {rid for rid, _ in db.eval_updates()} == {"m1", "m2"}


def test_on_demand_generation_never_blocked_by_skip(monkeypatch):
    db = _pipeline_db()
    db.matches = [{"id": "m1", "job_id": "j1", "rank": 1, "optimized_resume_text": None}]
    _patch_optimizer(monkeypatch, db, verdicts={"Product Designer": "skip"})

    ok = asyncio.run(optimizer.run_optimizer_for_match("u1", "m1"))

    assert ok is True
    # The verdict is stored (shows as a caution in the UI)…
    assert {rid for rid, _ in db.eval_updates()} == {"m1"}
    # …but the resume the user explicitly asked for is still generated.
    assert [rid for rid, _ in db.resume_updates()] == ["m1"]
