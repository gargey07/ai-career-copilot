"""
GET /api/admin/test-fetch — the "why zero jobs for this category?" probe.

The endpoint's value is separating the stages: what Adzuna returned raw,
what the title filter kept, what the store already has. The live Adzuna
call itself is stubbed (_adzuna_probe is isolated for exactly this).
"""
from __future__ import annotations
import asyncio

import pytest
from fastapi import HTTPException

import api.routes.admin as admin_module
from api.routes.admin import test_fetch as run_test_fetch


class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _FakeSupabase:
    def __init__(self, stored_count=7):
        self._stored_count = stored_count

    def table(self, name):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def insert(self, *a, **k):
        return self

    def execute(self):
        return _Resp([], count=self._stored_count)


def _patch(monkeypatch, titles_by_query, stored_count=7, budget_ok=True):
    monkeypatch.setattr(admin_module.settings, "admin_token", "secret")
    monkeypatch.setattr(admin_module.settings, "adzuna_app_id", "id")
    monkeypatch.setattr(admin_module.settings, "adzuna_app_key", "key")
    monkeypatch.setattr(admin_module, "get_supabase", lambda: _FakeSupabase(stored_count))

    async def fake_probe(query, country, where):
        return titles_by_query.get(query, [])
    monkeypatch.setattr(admin_module, "_adzuna_probe", fake_probe)

    import core.usage_guard as usage_guard
    monkeypatch.setattr(usage_guard, "check_budget", lambda *a, **k: budget_ok)


def test_fetch_reports_raw_vs_filtered_counts(monkeypatch):
    # "HR" returns 3 raw of which 2 pass the title filter; "Recruiter"
    # returns recruiter titles that all pass. (hr_recruiter's first three
    # queries are HR / Human Resources / Recruiter.)
    _patch(monkeypatch, {
        "HR": ["HR Executive", "HR Generalist", "Office Cleaner"],
        "Human Resources": ["Human Resources Executive"],
        "Recruiter": ["Senior Recruiter"],
    })

    result = asyncio.run(run_test_fetch(token="secret", category="hr_recruiter", location=""))

    assert result["category"] == "hr_recruiter"
    assert result["jobs_stored_for_category"] == 7
    by_query = {r["query"]: r for r in result["results"]}
    hr = by_query["HR"]
    assert hr["adzuna_raw"] == 3
    assert hr["passed_title_filter"] == 2  # Office Cleaner rejected
    assert "Office Cleaner" not in hr["sample_passing_titles"]
    assert by_query["Human Resources"]["passed_title_filter"] == 1
    assert by_query["Recruiter"]["passed_title_filter"] == 1


def test_fetch_flags_empty_adzuna_result(monkeypatch):
    _patch(monkeypatch, {})  # every query -> zero raw results
    result = asyncio.run(run_test_fetch(token="secret", category="hr_recruiter", location=""))
    assert all(r["adzuna_raw"] == 0 and r["error"] is None for r in result["results"])


def test_fetch_reports_missing_keys_instead_of_calling(monkeypatch):
    _patch(monkeypatch, {"HR Manager": ["HR Executive"]})
    monkeypatch.setattr(admin_module.settings, "adzuna_app_id", "")
    result = asyncio.run(run_test_fetch(token="secret", category="hr_recruiter", location=""))
    assert all("not configured" in (r["error"] or "") for r in result["results"])


def test_fetch_requires_admin_token(monkeypatch):
    _patch(monkeypatch, {})
    with pytest.raises(HTTPException) as e:
        asyncio.run(run_test_fetch(token="wrong", category="hr_recruiter", location=""))
    assert e.value.status_code == 403
