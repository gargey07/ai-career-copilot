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
import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional

import google.generativeai as genai

from core.config import get_settings
from core.usage_guard import check_budget, record_usage_event, BudgetExceededError

logger = logging.getLogger(__name__)
settings = get_settings()

# Rate limiting: Gemini free tier = 15 RPM
_GEMINI_MIN_DELAY = 4.0  # seconds between requests (60s / 15 RPM = 4s)
_last_gemini_call = 0.0

# The openai SDK's default timeout is 600s (connect=5, read/write/pool=600).
# A provider that's reachable but silently hangs on the read (rather than
# cleanly erroring) would tie up the waterfall for up to 10 minutes before
# falling through to the next one — with several fallbacks configured that
# compounds fast. A resume/cover-letter generation is one short completion
# call; if it hasn't answered in 25s, treat it as failed and move on.
_PROVIDER_TIMEOUT_SECONDS = 25.0


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
        self.name = "gemini"  # waterfall log lines + '{name}_fail' usage bucket
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        self.embed_model = "models/gemini-embedding-001"
        logger.info("✅ Gemini AI provider initialized (gemini-2.5-flash)")

    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        """
        Calls Gemini to generate text.
        Automatically respects the 15 RPM rate limit with sleep().

        google-generativeai's client is fully synchronous — genai.*() calls
        are real blocking network I/O, not asyncio-compatible despite this
        method's `async def`. Uvicorn runs a single worker here (no
        --workers flag), so a blocking call anywhere doesn't just slow its
        own request — it freezes the ENTIRE event loop, including brand
        new incoming connections, for its full duration. This was the
        actual cause of the nightly pipeline's "curl: (28) Connection
        timed out after 120000ms" with zero response: a prior/concurrent
        pipeline run's chain of blocking Gemini calls (each up to
        _PROVIDER_TIMEOUT_SECONDS, plus up to 4s of rate-limit sleep,
        serially, one per job/user) monopolized the only thread handling
        HTTP, so the server couldn't even accept the new TCP connection
        until that chain finished — easily longer than 120s for a full
        run. asyncio.to_thread() below moves the blocking call to a
        worker thread so the event loop stays free to serve other
        requests while this one is in flight.
        """
        if not check_budget("gemini_generate", settings.gemini_generate_daily_limit):
            raise BudgetExceededError("Gemini generate_text daily budget exhausted")

        global _last_gemini_call

        # Rate limiting: enforce minimum delay between calls — await, not
        # time.sleep(), so this wait doesn't freeze the event loop either.
        elapsed = time.time() - _last_gemini_call
        if elapsed < _GEMINI_MIN_DELAY:
            wait = _GEMINI_MIN_DELAY - elapsed
            logger.debug(f"⏳ Gemini rate limit: waiting {wait:.1f}s")
            await asyncio.sleep(wait)

        try:
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(temperature=temperature),
                request_options={"timeout": _PROVIDER_TIMEOUT_SECONDS},
            )
            _last_gemini_call = time.time()
            return response.text.strip()
        except Exception as e:
            logger.error(f"❌ Gemini generate_text failed: {e}")
            raise

    async def embed_text(self, text: str) -> list[float]:
        """Embeds text using Gemini's text-embedding model. See
        generate_text's docstring — same blocking-SDK-in-a-single-worker
        issue applies here, same asyncio.to_thread fix."""
        if not check_budget("gemini_embed", settings.gemini_embed_daily_limit):
            raise BudgetExceededError("Gemini embed_text daily budget exhausted")
        try:
            result = await asyncio.to_thread(
                genai.embed_content,
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
        # max_retries=0: our own waterfall already fails over to the next
        # PROVIDER on any error, so the SDK's built-in retry-with-backoff on
        # this same provider (e.g. ~20-30s waits on a 429, observed live)
        # only adds latency without adding a real chance of success — Gemini's
        # 20/day quota or another provider's rate limit doesn't clear in 30s.
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=_PROVIDER_TIMEOUT_SECONDS, max_retries=0)
        self.name = "openai"  # waterfall log lines + '{name}_fail' usage bucket
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
        # max_retries=0 — see the matching comment on OpenAIProvider above;
        # our waterfall is the retry strategy, the SDK's own retry on this
        # same rate-limited provider is pure added latency.
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=_PROVIDER_TIMEOUT_SECONDS, max_retries=0)

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
        (settings.cohere_api_key, "cohere", "https://api.cohere.ai/compatibility/v1",
         settings.cohere_model, settings.cohere_daily_limit),
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
    Tries each provider in `fallbacks` order for generate_text. Any failure
    — rate limit, our own daily budget cap, network error, provider outage —
    falls through to the next one rather than aborting the whole match.
    embed_text always goes straight to `primary` (Gemini); mixing embedding
    spaces would silently corrupt pgvector similarity search against jobs
    already embedded with Gemini, and Gemini's embedding quota is separate
    from its (tiny, 20/day) generation quota.
    """

    def __init__(self, embedder: AIProvider, chain: list[AIProvider]):
        self._primary = embedder
        self._chain = chain

    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        last_error: Exception | None = None
        for provider in self._chain:
            try:
                return await provider.generate_text(prompt, temperature)
            except Exception as e:
                name = getattr(provider, "name", type(provider).__name__)
                # Exception class distinguishes 401 vs 429 vs timeout in the
                # log; the _fail counter surfaces the same fact on the admin
                # usage screen so diagnosing this never requires log access.
                logger.warning(f"⚠️  {name} failed ({type(e).__name__}: {e}) — trying next provider in the waterfall")
                record_usage_event(f"{name}_fail")
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

    When AI_PROVIDER=gemini (the default), text generation runs through a
    waterfall in this order: Groq FIRST (its free tier is ~50x larger than
    Gemini's real 20-requests/day generation quota, measured in production),
    then Gemini, then OpenRouter / GitHub Models / Mistral / Cohere, with
    OpenAI last if its key is set. Providers without a configured key are
    skipped. Embeddings always go to Gemini regardless (separate quota, and
    pgvector vectors must stay in one embedding space).
    AI_PROVIDER=openai opts fully out of the waterfall (unchanged behavior).
    """
    global _provider_instance
    if _provider_instance is None:
        provider = settings.ai_provider.lower()
        if provider == "gemini":
            gemini = GeminiProvider()
            others = _build_fallback_providers()
            groq = [p for p in others if getattr(p, "name", "") == "groq"]
            rest = [p for p in others if getattr(p, "name", "") != "groq"]
            chain: list[AIProvider] = [*groq, gemini, *rest]
            if settings.openai_api_key:
                chain.append(OpenAIProvider())
            _provider_instance = WaterfallAIProvider(gemini, chain) if len(chain) > 1 else gemini
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
