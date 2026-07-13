"""
AI job requirement classifier — parsing, failure contract, and the
pipeline's targeting of only the genuinely-unknown residual bucket.

2026-07: the founder asked for AI to help with the biggest remaining
issue — experience-level accuracy — after the free regex/title pass
(jobs/fetchers.py) was already widened. This is that AI fallback: a
JOB-level classifier (runs once per ambiguous job, not once per user),
feeding the same core/matcher.py gate the regex pass already feeds.
"""
from __future__ import annotations
import asyncio
import json

import core.job_classifier as job_classifier
from core.job_classifier import classify_job, parse_classification


# ── parse_classification ────────────────────────────────────────────────────
def test_parse_clean_json():
    raw = json.dumps({"required_experience_months": 24, "seniority_level": "mid"})
    result = parse_classification(raw)
    assert result == {"required_experience_months": 24, "seniority_level": "mid"}


def test_parse_fenced_json():
    raw = "```json\n" + json.dumps({"required_experience_months": 60, "seniority_level": "senior"}) + "\n```"
    assert parse_classification(raw)["required_experience_months"] == 60


def test_parse_both_null_is_a_failed_classification():
    # Nothing usable at all — treat exactly like a parse failure, not a
    # "confirmed no requirement" (matcher.py's contract: None means
    # unknown, never "no requirement").
    raw = json.dumps({"required_experience_months": None, "seniority_level": None})
    assert parse_classification(raw) is None


def test_parse_partial_result_kept():
    raw = json.dumps({"required_experience_months": None, "seniority_level": "entry"})
    result = parse_classification(raw)
    assert result == {"required_experience_months": None, "seniority_level": "entry"}


def test_parse_garbage_returns_none():
    assert parse_classification("Sure, this role needs about 5 years.") is None
    assert parse_classification("") is None
    assert parse_classification("{not json") is None


def test_parse_invalid_seniority_dropped():
    raw = json.dumps({"required_experience_months": 12, "seniority_level": "junior-ish"})
    result = parse_classification(raw)
    assert result == {"required_experience_months": 12, "seniority_level": None}


def test_parse_implausible_months_dropped():
    raw = json.dumps({"required_experience_months": 999, "seniority_level": "senior"})
    result = parse_classification(raw)
    assert result == {"required_experience_months": None, "seniority_level": "senior"}


# ── classify_job failure contract ───────────────────────────────────────────
class _FakeProvider:
    def __init__(self, response=None, error=None):
        self._response, self._error = response, error
        self.calls = 0

    async def generate_text(self, prompt, temperature=0.3):
        self.calls += 1
        if self._error:
            raise self._error
        return self._response


_JOB = {"id": "j1", "title": "Backend Developer", "description": "You'll mentor junior engineers on our platform team."}


def test_classify_job_happy_path(monkeypatch):
    monkeypatch.setattr(job_classifier, "check_budget", lambda *a, **k: True)
    provider = _FakeProvider(response=json.dumps({"required_experience_months": 60, "seniority_level": "senior"}))
    monkeypatch.setattr(job_classifier, "get_ai_provider", lambda: provider)
    result = asyncio.run(classify_job(_JOB))
    assert result == {"required_experience_months": 60, "seniority_level": "senior"}
    assert provider.calls == 1


def test_classify_job_budget_exhausted_returns_none_without_calling_provider(monkeypatch):
    monkeypatch.setattr(job_classifier, "check_budget", lambda *a, **k: False)
    provider = _FakeProvider(response="{}")
    monkeypatch.setattr(job_classifier, "get_ai_provider", lambda: provider)
    assert asyncio.run(classify_job(_JOB)) is None
    assert provider.calls == 0  # budget checked BEFORE spending an AI call


def test_classify_job_provider_error_returns_none(monkeypatch):
    monkeypatch.setattr(job_classifier, "check_budget", lambda *a, **k: True)
    monkeypatch.setattr(job_classifier, "get_ai_provider", lambda: _FakeProvider(error=RuntimeError("boom")))
    assert asyncio.run(classify_job(_JOB)) is None


def test_classify_job_unparseable_returns_none(monkeypatch):
    monkeypatch.setattr(job_classifier, "check_budget", lambda *a, **k: True)
    monkeypatch.setattr(job_classifier, "get_ai_provider", lambda: _FakeProvider(response="I'd estimate mid-level."))
    assert asyncio.run(classify_job(_JOB)) is None


def test_classify_job_skips_when_nothing_to_judge(monkeypatch):
    provider = _FakeProvider(response=json.dumps({"required_experience_months": 12, "seniority_level": "entry"}))
    monkeypatch.setattr(job_classifier, "check_budget", lambda *a, **k: True)
    monkeypatch.setattr(job_classifier, "get_ai_provider", lambda: provider)
    assert asyncio.run(classify_job({"id": "j2", "title": "", "description": ""})) is None
    assert provider.calls == 0
