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


# ── Application-page enrichment (resolve_job_experience) ──────────────────────
# The real-world case this exists for: an Adzuna "Product Designer" whose
# API description says nothing about experience, while the company's own
# ATS page behind the apply link plainly states "Required Experience:
# 2 - 5 Years" (observed live on a PeopleStrong careers page, 2026-07).
from jobs.fetchers import _extract_page_text, experience_months_from_text, fetch_job_page_text
from core.job_classifier import resolve_job_experience

_ATS_PAGE_HTML = """
<html><head><title>Careers</title><script>var x = 1;</script>
<style>.a{color:red}</style></head>
<body><div class="job"><h1>Product Designer</h1>
<p>Posted On</p><p>02 Jun 2026</p>
<p>Required Experience</p><p>2 - 5 Years</p>
<button>Register And Apply</button></div></body></html>
"""


def test_ats_page_text_extraction_and_regex_end_to_end():
    text = _extract_page_text(_ATS_PAGE_HTML)
    assert "Required Experience" in text and "2 - 5 Years" in text
    assert "var x" not in text  # scripts/styles dropped
    assert experience_months_from_text(text) == 24


def test_fetch_page_text_rejects_non_http_urls_without_network():
    # JSearch rows without an apply link store synthetic "jsearch_<id>"
    # values in source_url — these must short-circuit to "" instantly.
    assert asyncio.run(fetch_job_page_text("jsearch_abc123")) == ""
    assert asyncio.run(fetch_job_page_text("")) == ""
    assert asyncio.run(fetch_job_page_text(None)) == ""


_ADZUNA_JOB = {
    "id": "j9",
    "title": "Product Designer",
    "description": "Authoring user journeys, wireframes, and visual design (UX/UI).",
    "source_url": "https://example-ats.test/job/105411",
}


def _explode_classify(*a, **k):
    raise AssertionError("AI must not be called when the page regex already answered")


def test_resolve_uses_page_regex_first_no_ai_call(monkeypatch):
    async def fake_page_text(url):
        return _extract_page_text(_ATS_PAGE_HTML)
    import jobs.fetchers as fetchers
    monkeypatch.setattr(fetchers, "fetch_job_page_text", fake_page_text)
    monkeypatch.setattr(job_classifier, "classify_job", _explode_classify)

    result = asyncio.run(resolve_job_experience(_ADZUNA_JOB))
    assert result == {"required_experience_months": 24, "seniority_level": None}


def test_resolve_falls_back_to_ai_with_page_text_as_context(monkeypatch):
    async def fake_page_text(url):
        return "Join our team of experts building the future of design tooling."  # no parseable years
    import jobs.fetchers as fetchers
    monkeypatch.setattr(fetchers, "fetch_job_page_text", fake_page_text)

    seen = {}
    async def fake_classify(job):
        seen["description"] = job["description"]
        return {"required_experience_months": 36, "seniority_level": "mid"}
    monkeypatch.setattr(job_classifier, "classify_job", fake_classify)

    result = asyncio.run(resolve_job_experience(_ADZUNA_JOB))
    assert result == {"required_experience_months": 36, "seniority_level": "mid"}
    # The AI saw BOTH the original description and the page text.
    assert "wireframes" in seen["description"]
    assert "design tooling" in seen["description"]


def test_resolve_with_unfetchable_page_still_tries_ai_on_description(monkeypatch):
    async def fake_page_text(url):
        return ""  # JS-only page / timeout / synthetic URL
    import jobs.fetchers as fetchers
    monkeypatch.setattr(fetchers, "fetch_job_page_text", fake_page_text)

    seen = {}
    async def fake_classify(job):
        seen["description"] = job["description"]
        return None
    monkeypatch.setattr(job_classifier, "classify_job", fake_classify)

    assert asyncio.run(resolve_job_experience(_ADZUNA_JOB)) is None
    assert seen["description"] == _ADZUNA_JOB["description"]  # unaugmented
