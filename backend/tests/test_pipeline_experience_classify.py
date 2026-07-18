"""
core.pipeline_runner._classify_unknown_experience_jobs — targets only the
residual bucket the free regex/title pass couldn't resolve, and never
lets a single unparseable job or an exhausted budget crash the pipeline.
"""
from __future__ import annotations
import asyncio

import core.pipeline_runner as pipeline_runner


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self.is_calls: list[tuple] = []

    def select(self, *a, **k):
        return self

    def is_(self, col, val):
        self.is_calls.append((col, val))
        return self

    def limit(self, n):
        return self

    def order(self, *a, **k):
        # Newest-first ordering (the batch-clog fix) — chain no-op here.
        return self

    def eq(self, *a, **k):
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def execute(self):
        if hasattr(self, "_update_payload"):
            return _Resp([])
        return _Resp(self._rows)


class _FakeSupabase:
    def __init__(self, rows):
        self._rows = rows
        self.updated: list[tuple[str, dict]] = []

    def table(self, name):
        q = _FakeQuery(self._rows)
        original_execute = q.execute

        def execute():
            if hasattr(q, "_update_payload"):
                self.updated.append((q._row_id, q._update_payload))
            return original_execute()

        q.execute = execute
        return q


def _rows():
    return [
        {"id": "j1", "title": "Backend Developer", "description": "You'll mentor junior engineers."},
        {"id": "j2", "title": "Weird posting with no signal", "description": "Great culture!"},
    ]


def test_only_queries_jobs_missing_both_columns(monkeypatch):
    db = _FakeSupabase([])
    monkeypatch.setattr(pipeline_runner, "get_supabase", lambda: db)

    query_conditions = []

    class _RecordingQuery(_FakeQuery):
        def is_(self, col, val):
            query_conditions.append((col, val))
            return super().is_(col, val)

    def table(name):
        return _RecordingQuery([])
    db.table = table

    asyncio.run(pipeline_runner._classify_unknown_experience_jobs())
    assert ("required_experience_months", "null") in query_conditions
    assert ("seniority_level", "null") in query_conditions


def test_classifies_and_writes_results(monkeypatch):
    rows = _rows()
    updated: list[tuple[str, dict]] = []

    class _Query(_FakeQuery):
        def eq(self, col, val):
            self._row_id = val
            return self

        def execute(self):
            if hasattr(self, "_update_payload"):
                updated.append((self._row_id, self._update_payload))
                return _Resp([])
            return _Resp(self._rows)

    class _DB:
        def table(self, name):
            return _Query(rows)

    monkeypatch.setattr(pipeline_runner, "get_supabase", lambda: _DB())

    async def fake_classify(job):
        if job["id"] == "j1":
            return {"required_experience_months": 60, "seniority_level": "senior"}
        return None  # genuinely unclassifiable — left alone

    import core.job_classifier as job_classifier
    monkeypatch.setattr(job_classifier, "classify_job", fake_classify)

    count = asyncio.run(pipeline_runner._classify_unknown_experience_jobs())
    assert count == 1
    assert updated == [("j1", {"required_experience_months": 60, "seniority_level": "senior"})]


def test_never_raises_when_job_classifier_unavailable(monkeypatch):
    def _broken_import(name, *a, **k):
        if name == "core.job_classifier":
            raise ImportError("no AI provider configured")
        return __import__(name, *a, **k)

    db = _FakeSupabase([])
    monkeypatch.setattr(pipeline_runner, "get_supabase", lambda: db)
    # Simulate the inline `from core.job_classifier import classify_job`
    # failing (e.g. missing dependency) by breaking the module attribute.
    import sys
    monkeypatch.setitem(sys.modules, "core.job_classifier", None)

    count = asyncio.run(pipeline_runner._classify_unknown_experience_jobs())
    assert count == 0
