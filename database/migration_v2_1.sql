-- ============================================================
-- AI Career Copilot — Schema Migration v2.1
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- Safe to re-run (uses IF NOT EXISTS / ALTER TABLE IF NOT EXISTS)
-- ============================================================

-- ── T-017: sent_job_ids on users ─────────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS
  sent_job_ids        TEXT[] DEFAULT '{}';       -- job UUIDs already sent in past digests

-- ── T-004: digest cooldown tracking on users ─────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS
  last_digest_sent_at TIMESTAMPTZ;               -- when we last successfully sent a digest

ALTER TABLE users ADD COLUMN IF NOT EXISTS
  unsubscribed_at     TIMESTAMPTZ;               -- when user unsubscribed

-- ── T-012: user-selectable digest time slot ───────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS
  preferred_digest_time TIME DEFAULT '07:00:00'; -- e.g. 06:00, 07:00, 09:00

-- ── T-003: unsubscribe tracking ──────────────────────────────────────────────
-- is_active column already exists; unsubscribed_at added above

-- ── T-011: soft-delete support ───────────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS
  status              TEXT DEFAULT 'active';     -- 'active', 'deleted'

ALTER TABLE users ADD COLUMN IF NOT EXISTS
  deleted_at          TIMESTAMPTZ;

-- ── T-020: PDF failure tracking on user_jobs ─────────────────────────────────
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS
  error_message       TEXT;                      -- error detail when status='failed'

-- ── T-022: cache tracking on user_jobs ───────────────────────────────────────
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS
  cache_hit           BOOLEAN DEFAULT FALSE;     -- was resume from 7-day cache?

-- ── T-008: resume feedback ────────────────────────────────────────────────────
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS
  feedback            TEXT;                      -- 'thumbs_up', 'thumbs_down', null

ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS
  feedback_reason     TEXT;                      -- chip reason if thumbs_down

ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS
  feedback_at         TIMESTAMPTZ;

-- ── Update status enum to include new statuses ────────────────────────────────
-- Added statuses: 'failed', 'needs_manual_trigger', 'pdf_ready'
-- (PostgreSQL TEXT columns accept any value — no enum change needed)

-- ── T-006: pgvector match_jobs function (enhanced) ───────────────────────────
-- Drop ALL existing overloads first (fixes "function name not unique" error)
DROP FUNCTION IF EXISTS match_jobs(vector, int);
DROP FUNCTION IF EXISTS match_jobs(vector(768), int);
DROP FUNCTION IF EXISTS match_jobs(vector, int, float);
DROP FUNCTION IF EXISTS match_jobs(vector, int, float, text[]);
DROP FUNCTION IF EXISTS match_jobs(vector(768), int, float, text[]);

-- Recreate with full signature: percentage scores, freshness filter, dedup-aware
CREATE FUNCTION match_jobs(
  query_embedding   vector(768),
  match_count       int     DEFAULT 5,
  min_score         float   DEFAULT 0.3,
  exclude_job_ids   text[]  DEFAULT '{}'::text[]
)
RETURNS TABLE (
  id              uuid,
  title           text,
  company         text,
  location        text,
  description     text,
  source_url      text,
  apply_url       text,
  career_page_url text,
  is_remote       boolean,
  posted_at       timestamptz,
  match_score     float
)
LANGUAGE sql STABLE AS $$
  SELECT
    j.id,
    j.title,
    j.company,
    j.location,
    j.description,
    j.source_url,
    j.apply_url,
    j.career_page_url,
    j.is_remote,
    j.posted_at,
    ROUND(((1 - (j.embedding <=> query_embedding)) * 100)::numeric, 2)::float AS match_score
  FROM jobs j
  WHERE
    j.embedding IS NOT NULL
    AND j.collected_at > NOW() - INTERVAL '7 days'
    AND (1 - (j.embedding <=> query_embedding)) >= min_score
    AND NOT (j.id::text = ANY(exclude_job_ids))
  ORDER BY j.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- Grant public read access (backend uses service_role, anon reads for frontend)
GRANT EXECUTE ON FUNCTION match_jobs TO anon, authenticated;

-- ── T-005: Pipeline run secrets table ────────────────────────────────────────
-- (cron auth is handled via header token — no DB table needed)

-- ── Indexes for new queries ───────────────────────────────────────────────────
-- Index for filtering users by digest time (T-005 cron)
CREATE INDEX IF NOT EXISTS users_is_active_digest_time_idx
  ON users (is_active, preferred_digest_time);

-- Index for cache lookup (T-022)
CREATE INDEX IF NOT EXISTS user_jobs_cache_lookup_idx
  ON user_jobs (user_id, job_id, status, digest_date DESC);

-- ============================================================
-- VERIFICATION QUERIES — run these to confirm migration worked
-- ============================================================
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users' ORDER BY ordinal_position;
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'user_jobs' ORDER BY ordinal_position;
-- SELECT proname FROM pg_proc WHERE proname = 'match_jobs';
