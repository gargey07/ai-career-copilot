"""
AI Career Copilot — Application Settings
Loaded from .env file using pydantic-settings
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    founder_email: str = "gargeypatel123@gmail.com"
    digest_time: str = "07:00"
    max_jobs_per_user: int = 10
    ai_jobs_per_user: int = 3

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
