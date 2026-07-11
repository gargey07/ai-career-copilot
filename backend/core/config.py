"""
AI Career Copilot — Application Settings
Loaded from .env file using pydantic-settings
"""
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Dashboard copy-paste repeatedly wrapped values in angle brackets or
    # left stray whitespace/quotes (e.g. "<https://x.supabase.co>"), which
    # produces "Invalid URL" errors deep in the Supabase/httpx client.
    # Strip that junk off every string setting up front so a fat-fingered
    # env var can't silently break the whole backend.
    @field_validator("*", mode="before")
    @classmethod
    def _strip_wrapping_chars(cls, v):
        if isinstance(v, str):
            return v.strip().strip("<>").strip().strip('"').strip("'").strip()
        return v

    # App
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    frontend_url: str = ""
    # Own public URL — needed to build the unsubscribe link and the apply-click
    # redirect link that ship inside emails (those must point at the backend
    # directly, not the frontend). Falls back to the current Coolify/Hostinger
    # URL if BACKEND_URL is unset on the server, same pattern as frontend_url —
    # migrated off Render 2026-07-10, HTTPS enabled 2026-07-10; set BACKEND_URL
    # explicitly once a real domain is pointed at the VPS instead of relying
    # on this fallback.
    backend_url: str = "https://n99tn44btm3ff0rx5pppaoqp.200.97.165.139.sslip.io"
    founder_email: str = "gargeypatel123@gmail.com"
    digest_time: str = "07:00"
    max_jobs_per_user: int = 10
    ai_jobs_per_user: int = 3
    # Each active category gets this many distinct search queries per fetch
    # run (was hardcoded to 1) — a deeper per-category pool means fewer
    # "no relevant jobs today" digests now that matching enforces category
    # relevance instead of padding with other categories' jobs.
    fetch_queries_per_category: int = 2

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""

    # Local DB (Docker dev)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_career_copilot"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Job APIs
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    jsearch_api_key: str = ""

    # Email finding
    hunter_api_key: str = ""

    # AI
    gemini_api_key: str = ""
    openai_api_key: str = ""
    ai_provider: str = "gemini"  # 'gemini' | 'openai'
    # Cover letters double the Gemini calls per match and nothing user-facing
    # shows them yet (admin Inspect only) — keep off until they ship.
    generate_cover_letters: bool = False

    # Text-generation fallback waterfall — used only when AI_PROVIDER=gemini
    # (the default) and only for generate_text (resume/cover-letter writing).
    # When Gemini errors or hits its rate limit mid-pipeline, the next
    # configured provider here is tried automatically. Embeddings always
    # stay on Gemini regardless — mixing embedding spaces would break
    # pgvector cosine-similarity against jobs already embedded with Gemini.
    # Empty key = that provider is skipped in the waterfall (safe to leave
    # any/all of these blank). All five speak the OpenAI chat-completions
    # API shape, so no extra SDK is needed beyond the existing `openai` pkg.
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_daily_limit: int = 500

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_daily_limit: int = 50

    github_models_token: str = ""
    github_models_model: str = "gpt-4o-mini"
    github_models_daily_limit: int = 60

    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    mistral_daily_limit: int = 500

    cohere_api_key: str = ""
    cohere_model: str = "command-r-plus-08-2024"
    cohere_daily_limit: int = 500

    # Storage
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "ai-copilot-resumes"
    r2_public_url: str = ""

    # Email sending
    resend_api_key: str = ""
    email_from: str = "hello@example.com"
    email_from_name: str = "AI Career Copilot"
    gmail_user: str = ""
    gmail_app_password: str = ""

    # Daily API budget caps — 0 means unlimited. Defaults are conservative
    # estimates for common free tiers; check your actual plan and adjust
    # via env vars rather than editing code.
    adzuna_daily_limit: int = 200          # Adzuna free tier
    jsearch_daily_limit: int = 5           # RapidAPI JSearch free tiers are usually ~150/month
    # Google's own 429 response on this free-tier key reports the REAL cap:
    # "GenerateRequestsPerDayPerProjectPerModel-FreeTier ... limit: 20,
    # model: gemini-2.5-flash" (observed 2026-07-10) — 1000 was an
    # aspirational placeholder that let check_budget wave every call through
    # long after Google itself was already rejecting them, burning a real
    # network round-trip on a guaranteed-429 for the rest of every day past
    # the ~20th generate call. Raise this via env var if the key is ever
    # upgraded off the free tier.
    gemini_generate_daily_limit: int = 20
    gemini_embed_daily_limit: int = 500
    openai_daily_limit: int = 50           # spend safety valve — OpenAI has no free quota
    resend_daily_limit: int = 100          # Resend free tier
    gmail_daily_limit: int = 100           # stay far under Gmail's ~500/day send cap
    resume_parse_daily_limit_per_ip: int = 10  # abuse/cost guard on re-uploads; keyed by client IP (no auth yet)
    # /resumes/confirm schedules real job fetching + AI generation; without a
    # cap, repeated unauthenticated confirms could drain the whole day's
    # budget. Generous enough for a signup plus several profile edits.
    profile_confirm_daily_limit_per_ip: int = 10
    # On-demand generation (per-job dashboard buttons) — separate small caps
    # on top of the pipeline's AI_JOBS_PER_USER so one user can't drain the
    # provider budget by hammering Generate.
    on_demand_resume_bonus_per_day: int = 2      # extra resumes beyond the pipeline quota
    cover_letters_per_user_daily: int = 3
    # Resume style preview (POST /api/resumes/preview) — no AI/Chromium
    # involved, cheap, but unauthenticated (fires pre-account during
    # onboarding), so still worth a sane per-IP daily ceiling.
    resume_preview_daily_limit_per_ip: int = 200

    # Shared secret to authorize the manual pipeline trigger (POST /api/admin/run-pipeline).
    # Empty = trigger disabled (safe default). Set ADMIN_TOKEN on the server to enable.
    admin_token: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — import this everywhere."""
    return Settings()
