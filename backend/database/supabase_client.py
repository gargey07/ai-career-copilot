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
        if not settings.supabase_url or not settings.supabase_service_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
            )
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
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
