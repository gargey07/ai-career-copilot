"""
AI Provider Abstraction Layer
─────────────────────────────
All AI calls go through this interface.
Swap providers (Gemini → OpenAI → Claude) in one place — zero business logic changes.

Usage:
    from core.ai import get_ai_provider
    ai = get_ai_provider()
    text = await ai.generate_text(prompt)
    embedding = await ai.embed_text(resume_text)
"""
from __future__ import annotations
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional

import google.generativeai as genai

from core.config import get_settings
from core.usage_guard import check_budget, BudgetExceededError

logger = logging.getLogger(__name__)
settings = get_settings()

# Rate limiting: Gemini free tier = 15 RPM
_GEMINI_MIN_DELAY = 4.0  # seconds between requests (60s / 15 RPM = 4s)
_last_gemini_call = 0.0


# ── Abstract Base ─────────────────────────────────────────────────────────────
class AIProvider(ABC):
    """Abstract base class for all AI providers."""

    @abstractmethod
    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        """Generate text from a prompt."""
        ...

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Convert text to a vector embedding."""
        ...


# ── Gemini Provider ───────────────────────────────────────────────────────────
class GeminiProvider(AIProvider):
    """Google Gemini AI provider (Gemini 1.5 Flash — free tier)."""

    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        self.embed_model = "models/gemini-embedding-001"
        logger.info("✅ Gemini AI provider initialized (gemini-2.5-flash)")

    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        """
        Calls Gemini to generate text.
        Automatically respects the 15 RPM rate limit with sleep().
        """
        if not check_budget("gemini_generate", settings.gemini_generate_daily_limit):
            raise BudgetExceededError("Gemini generate_text daily budget exhausted")

        global _last_gemini_call

        # Rate limiting: enforce minimum delay between calls
        elapsed = time.time() - _last_gemini_call
        if elapsed < _GEMINI_MIN_DELAY:
            wait = _GEMINI_MIN_DELAY - elapsed
            logger.debug(f"⏳ Gemini rate limit: waiting {wait:.1f}s")
            time.sleep(wait)

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(temperature=temperature),
            )
            _last_gemini_call = time.time()
            return response.text.strip()
        except Exception as e:
            logger.error(f"❌ Gemini generate_text failed: {e}")
            raise

    async def embed_text(self, text: str) -> list[float]:
        """Embeds text using Gemini's text-embedding model."""
        if not check_budget("gemini_embed", settings.gemini_embed_daily_limit):
            raise BudgetExceededError("Gemini embed_text daily budget exhausted")
        try:
            result = genai.embed_content(
                model=self.embed_model,
                content=text,
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=768,  # match vector(768) in Supabase schema
            )
            return result["embedding"]
        except Exception as e:
            logger.error(f"❌ Gemini embed_text failed: {e}")
            raise


# ── OpenAI Provider (Fallback) ────────────────────────────────────────────────
class OpenAIProvider(AIProvider):
    """OpenAI provider — used as fallback if Gemini is unavailable."""

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        logger.info("✅ OpenAI provider initialized")

    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        if not check_budget("openai", settings.openai_daily_limit):
            raise BudgetExceededError("OpenAI daily budget exhausted")
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()

    async def embed_text(self, text: str) -> list[float]:
        if not check_budget("openai", settings.openai_daily_limit):
            raise BudgetExceededError("OpenAI daily budget exhausted")
        response = await self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding


# ── Generic OpenAI-compatible chat provider (Groq / OpenRouter / GitHub
#    Models / Mistral) ─────────────────────────────────────────────────────────
class _ChatCompletionsProvider(AIProvider):
    """
    Groq, OpenRouter, GitHub Models, and Mistral all expose an
    OpenAI-compatible /chat/completions endpoint — same request/response
    shape, just a different base_url, api_key, and model name. One class
    covers all four instead of writing a near-identical SDK wrapper per
    provider.

    Generation-only: these are fallbacks for generate_text (resume/cover-
    letter writing) when Gemini rate-limits, not embedding providers —
    embed_text always stays on Gemini so vectors stay comparable in
    pgvector against jobs already embedded with Gemini.
    """

    def __init__(self, name: str, api_key: str, base_url: str, model: str, daily_limit: int):
        from openai import AsyncOpenAI
        self.name = name
        self.model = model
        self.daily_limit = daily_limit
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        if not check_budget(self.name, self.daily_limit):
            raise BudgetExceededError(f"{self.name} daily budget exhausted")
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()

    async def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError(f"{self.name} is a generate_text-only fallback — embeddings stay on Gemini.")


def _build_fallback_providers() -> list[AIProvider]:
    """
    Every optional fallback provider whose API key is actually configured,
    in a fixed priority order. Missing keys are skipped silently — this is
    how you add/remove a provider from the waterfall without touching code,
    just by setting or clearing its env var on Render.
    """
    candidates = [
        (settings.groq_api_key, "groq", "https://api.groq.com/openai/v1",
         settings.groq_model, settings.groq_daily_limit),
        (settings.openrouter_api_key, "openrouter", "https://openrouter.ai/api/v1",
         settings.openrouter_model, settings.openrouter_daily_limit),
        (settings.github_models_token, "github_models", "https://models.github.ai/inference",
         settings.github_models_model, settings.github_models_daily_limit),
        (settings.mistral_api_key, "mistral", "https://api.mistral.ai/v1",
         settings.mistral_model, settings.mistral_daily_limit),
    ]
    providers = []
    for api_key, name, base_url, model, daily_limit in candidates:
        if api_key:
            providers.append(_ChatCompletionsProvider(name, api_key, base_url, model, daily_limit))
            logger.info(f"✅ {name} fallback provider configured (model: {model})")
    return providers


# ── Waterfall ──────────────────────────────────────────────────────────────────
class WaterfallAIProvider(AIProvider):
    """
    Tries Gemini first, then each configured fallback provider in order,
    for generate_text only. Any failure — rate limit, our own daily budget
    cap, network error, provider outage — falls through to the next one
    rather than aborting the whole match. embed_text always goes straight
    to Gemini; mixing embedding spaces would silently corrupt pgvector
    similarity search against jobs already embedded with Gemini.
    """

    def __init__(self, primary: AIProvider, fallbacks: list[AIProvider]):
        self._primary = primary
        self._chain = [primary, *fallbacks]

    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        last_error: Exception | None = None
        for provider in self._chain:
            try:
                return await provider.generate_text(prompt, temperature)
            except Exception as e:
                name = getattr(provider, "name", type(provider).__name__)
                logger.warning(f"⚠️  {name} failed ({e}) — trying next provider in the waterfall")
                last_error = e
        raise last_error or RuntimeError("All AI providers in the waterfall failed")

    async def embed_text(self, text: str) -> list[float]:
        return await self._primary.embed_text(text)


# ── Factory ───────────────────────────────────────────────────────────────────
_provider_instance: Optional[AIProvider] = None


def get_ai_provider() -> AIProvider:
    """
    Returns the configured AI provider as a singleton.
    Provider is set via AI_PROVIDER env var: 'gemini' | 'openai'

    When AI_PROVIDER=gemini (the default), Gemini is wrapped in a waterfall
    with any of GROQ_API_KEY / OPENROUTER_API_KEY / GITHUB_MODELS_TOKEN /
    MISTRAL_API_KEY that are configured, plus OpenAI last if its key is set
    too — so a Gemini rate limit mid-pipeline no longer stalls resume
    generation for everyone behind it in the queue. AI_PROVIDER=openai opts
    fully out of Gemini and the waterfall (unchanged behavior).
    """
    global _provider_instance
    if _provider_instance is None:
        provider = settings.ai_provider.lower()
        if provider == "gemini":
            gemini = GeminiProvider()
            fallbacks = _build_fallback_providers()
            if settings.openai_api_key:
                fallbacks.append(OpenAIProvider())
            _provider_instance = WaterfallAIProvider(gemini, fallbacks) if fallbacks else gemini
        elif provider == "openai":
            _provider_instance = OpenAIProvider()
        else:
            raise ValueError(f"Unknown AI provider: '{provider}'. Use 'gemini' or 'openai'.")
    return _provider_instance


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()

    async def test():
        ai = get_ai_provider()
        print(f"Testing provider: {settings.ai_provider}")

        result = await ai.generate_text("Say 'AI Career Copilot is ready!' in one sentence.")
        print(f"✅ Text generation: {result}")

        embedding = await ai.embed_text("UI/UX Designer with 3 years experience in Figma")
        print(f"✅ Embedding: {len(embedding)} dimensions")

    asyncio.run(test())
