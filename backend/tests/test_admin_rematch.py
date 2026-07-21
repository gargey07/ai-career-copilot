"""
POST /api/admin/users/{id}/rematch — targeted fetch+match+generate for one
user (the "this person is stuck at zero jobs" fix). The endpoint schedules
background work and returns immediately; _rematch_user is the real logic.
"""
from __future__ import annotations
import asyncio

import pytest
from fastapi import HTTPException

import api.routes.admin as admin_module
from api.routes.admin import _rematch_user, rematch_user_now


class _BG:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *a, **k):
        self.tasks.append((fn, a, k))


def test_rematch_endpoint_schedules_and_requires_admin(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_token", "secret")

    bg = _BG()
    result = asyncio.run(rematch_user_now("u1", background_tasks=bg, token="secret"))
    assert result["status"] == "started"
    # audit + the actual re-match both scheduled, none run inline.
    assert any(fn is _rematch_user for fn, _, _ in bg.tasks)

    with pytest.raises(HTTPException) as e:
        asyncio.run(rematch_user_now("u1", background_tasks=_BG(), token="wrong"))
    assert e.value.status_code == 403


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeSupabase:
    def __init__(self, row):
        self._row = row

    def table(self, n):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def single(self):
        return self

    def execute(self):
        return _Resp(self._row)


def test_rematch_user_runs_fetch_match_generate(monkeypatch):
    calls = {"fetch": [], "match": 0, "store": 0, "generate": 0}

    monkeypatch.setattr(admin_module, "get_supabase",
                        lambda: _FakeSupabase({"job_category": "hr_recruiter", "preferred_locations": []}))
    monkeypatch.setattr(admin_module.settings, "fetch_queries_per_category", 3)

    import core.pipeline_runner as pr
    import jobs.fetchers as fetchers
    import core.matcher as matcher

    monkeypatch.setattr(pr, "_queries_for_category", lambda c: ["HR", "Human Resources", "Recruiter", "Talent Acquisition"])
    monkeypatch.setattr(fetchers, "resolve_fetch_location", lambda raw: None)

    async def fake_fetch(query, category, location):
        calls["fetch"].append(query)
        return 5
    monkeypatch.setattr(fetchers, "run_all_fetchers", fake_fetch)

    async def fake_match(uid):
        calls["match"] += 1
        return [{"job_id": "j1"}]
    monkeypatch.setattr(matcher, "match_jobs_for_user", fake_match)

    async def fake_store(uid, m):
        calls["store"] += 1
        return len(m)
    monkeypatch.setattr(matcher, "store_matches", fake_store)

    async def fake_generate(uid):
        calls["generate"] += 1
        return {"resumes": 1}
    monkeypatch.setattr(pr, "generate_resumes_for_user", fake_generate)

    asyncio.run(_rematch_user("u1"))

    # Only the top 3 queries run (not the 4th), then match + store + generate.
    assert calls["fetch"] == ["HR", "Human Resources", "Recruiter"]
    assert calls["match"] == 1 and calls["store"] == 1 and calls["generate"] == 1


def test_rematch_user_never_raises_on_failure(monkeypatch):
    # A user that can't be loaded must log and return, not crash.
    class _Boom(_FakeSupabase):
        def execute(self):
            raise RuntimeError("db down")
    monkeypatch.setattr(admin_module, "get_supabase", lambda: _Boom({}))
    asyncio.run(_rematch_user("u1"))  # no exception = pass
