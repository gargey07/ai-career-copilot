"""
Supabase Client — Single connection shared across the backend.
Uses service_role key so it bypasses Row Level Security (RLS).
"""
from __future__ import annotations
import os
from supabase import create_client, Client
from core.config import get_settings


_client: Client | None = None


def get_supabase() -> Client:
    """
    Returns a cached Supabase client using the service_role key.
    Call this function in every module that needs database access.
    """
    global _client
    if _client is None:
        settings = get_settings()
        url = settings.supabase_url
        if not url or not settings.supabase_service_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must both be set as environment variables."
            )
        # Catch the common wrong value: the dashboard page URL instead of the
        # project API URL. The API URL is https://<project-ref>.supabase.co —
        # NOT https://supabase.com/dashboard/project/<ref>.
        if "supabase.com/dashboard" in url or not url.rstrip("/").endswith(".supabase.co"):
            raise ValueError(
                f"SUPABASE_URL looks wrong ({url!r}). It must be your project API URL, "
                "which looks like https://<project-ref>.supabase.co — not the dashboard page URL."
            )
        _client = create_client(url, settings.supabase_service_key)
    return _client


# ── Quick connection test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    """Run this directly to test Supabase connection:
       python database/supabase_client.py
    """
    import sys

    # Load .env from parent directory during standalone test
    from dotenv import load_dotenv
    load_dotenv()

    try:
        client = get_supabase()
        # Simple probe: count rows in users table
        response = client.table("users").select("id", count="exact").execute()
        print(f"✅ Connected to Supabase successfully!")
        print(f"   Users in database: {response.count}")
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        sys.exit(1)
