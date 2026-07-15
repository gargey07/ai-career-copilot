"""
probe_all_providers — the admin "why is this key failing" diagnostic.

Context (2026-07-15 admin usage screen): OpenRouter showed 10 used /
10 failed and GitHub Models 10 used / 10 failed — every attempt failing
is a config problem (bad key / wrong model ID), not a quota, but the
usage counters can't say WHICH. The probe fires one call per configured
provider and returns each one's real error text.
"""
from __future__ import annotations
import asyncio

import core.ai as ai_module
from core.ai import probe_all_providers


class _FakeProvider:
    def __init__(self, name, error=None, response="OK"):
        self.name = name
        self._error = error
        self._response = response

    async def generate_text(self, prompt, temperature=0.3):
        if self._error:
            raise self._error
        return self._response


def test_probe_reports_ok_and_error_per_provider(monkeypatch):
    fakes = [
        _FakeProvider("groq"),
        _FakeProvider("openrouter", error=RuntimeError("404 No endpoints found for meta-llama/llama-3.3-70b-instruct:free")),
        _FakeProvider("github_models", error=RuntimeError("unknown_model: gpt-4o-mini")),
    ]
    monkeypatch.setattr(ai_module, "_build_fallback_providers", lambda: fakes)
    monkeypatch.setattr(ai_module.settings, "gemini_api_key", "")
    monkeypatch.setattr(ai_module.settings, "openai_api_key", "")

    results = asyncio.run(probe_all_providers())
    by_name = {r["provider"]: r for r in results}
    assert by_name["groq"]["ok"] is True
    assert by_name["openrouter"]["ok"] is False
    assert "404" in by_name["openrouter"]["detail"]
    assert by_name["github_models"]["ok"] is False
    assert "unknown_model" in by_name["github_models"]["detail"]


def test_probe_with_nothing_configured(monkeypatch):
    monkeypatch.setattr(ai_module, "_build_fallback_providers", lambda: [])
    monkeypatch.setattr(ai_module.settings, "gemini_api_key", "")
    monkeypatch.setattr(ai_module.settings, "openai_api_key", "")
    results = asyncio.run(probe_all_providers())
    assert len(results) == 1
    assert results[0]["ok"] is False


def test_github_models_default_is_publisher_prefixed():
    """models.github.ai 404s on bare model names — the exact used==failed
    signature from the admin screen. The default must carry the publisher."""
    from core.config import Settings
    assert "/" in Settings().github_models_model
