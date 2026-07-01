-- ============================================================
-- AI Career Copilot - Database Schema v2.0
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- Enable pgvector extension for AI-powered job matching
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- USERS TABLE
-- Stores all registered users and their job search preferences
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email               TEXT UNIQUE NOT NULL,
  name                TEXT,
  avatar_url          TEXT,
  google_id           TEXT UNIQUE,

  -- Job preferences
  target_roles        TEXT[] DEFAULT '{}',        -- e.g. ['UI/UX Designer', 'Product Designer']
  experience_level    TEXT DEFAULT 'mid',          -- 'entry', 'mid', 'senior', 'lead'
  preferred_locations TEXT[] DEFAULT '{}',         -- e.g. ['Mumbai', 'Remote', 'Bangalore']
  salary_min          INTEGER,                     -- in INR/month or USD/year
  salary_max          INTEGER,
  remote_preference   TEXT DEFAULT 'any',          -- 'remote', 'hybrid', 'onsite', 'any'

  -- Resume data
  resume_text         TEXT,                        -- raw resume content (pasted or parsed from PDF)
  resume_embedding    vector(768),                 -- for matching

  -- Profile links
  linkedin_url        TEXT,
  portfolio_url       TEXT,
  github_url          TEXT,

  -- Account settings
  tier                TEXT DEFAULT 'free',         -- 'free', 'pro', 'enterprise'
  is_active           BOOLEAN DEFAULT TRUE,
  email_time          TIME DEFAULT '07:00:00',     -- preferred time for morning digest
  timezone            TEXT DEFAULT 'Asia/Kolkata',

  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- JOBS TABLE
-- Central job store — one record per unique job, shared across all users
-- ============================================================
CREATE TABLE IF NOT EXISTS jobs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source              TEXT NOT NULL,               -- 'adzuna', 'jsearch', 'remotive', 'wellfound'
  external_id         TEXT,                        -- original ID from source API
  source_url          TEXT UNIQUE NOT NULL,        -- original job URL (used for dedup)

  -- Core job info
  title               TEXT NOT NULL,
  company             TEXT,
  location            TEXT,
  description         TEXT,
  salary_min          INTEGER,
  salary_max          INTEGER,
  currency            TEXT DEFAULT 'INR',
  employment_type     TEXT,                        -- 'full-time', 'part-time', 'contract', 'internship'
  seniority_level     TEXT,                        -- 'entry', 'mid', 'senior', 'lead'
  is_remote           BOOLEAN DEFAULT FALSE,

  -- Contact / apply info
  company_email       TEXT,
  career_page_url     TEXT,
  apply_url           TEXT,

  -- AI / vector data
  embedding           vector(768),                 -- job description embedding for matching

  -- Timestamps
  posted_at           TIMESTAMPTZ,
  collected_at        TIMESTAMPTZ DEFAULT NOW(),
  expires_at          TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days')
);

-- Index for fast vector similarity search
CREATE INDEX IF NOT EXISTS jobs_embedding_idx
  ON jobs USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Index for filtering fresh jobs
CREATE INDEX IF NOT EXISTS jobs_collected_at_idx ON jobs (collected_at DESC);

-- ============================================================
-- USER_JOBS TABLE
-- Tracks which jobs were matched, processed, and applied per user
-- ============================================================
CREATE TABLE IF NOT EXISTS user_jobs (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id                  UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,

  -- Matching
  match_score             FLOAT,                   -- 0.0 to 1.0 cosine similarity score
  rank                    INTEGER,                 -- 1 = best match for this user today

  -- AI-generated content
  optimized_resume_text   TEXT,
  cover_letter_text       TEXT,
  pdf_url                 TEXT,                    -- signed URL to PDF in R2/S3

  -- Status tracking
  status                  TEXT DEFAULT 'matched',  -- 'matched', 'resume_ready', 'emailed', 'applied', 'interviewing', 'offered', 'rejected'
  applied_at              TIMESTAMPTZ,

  -- Meta
  digest_date             DATE DEFAULT CURRENT_DATE,  -- which day's digest this belongs to
  created_at              TIMESTAMPTZ DEFAULT NOW(),
  updated_at              TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(user_id, job_id, digest_date)             -- one record per user-job-day
);

-- ============================================================
-- EMAIL_LOGS TABLE
-- Tracks all outgoing emails for monitoring and debugging
-- ============================================================
CREATE TABLE IF NOT EXISTS email_logs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
  email_address TEXT NOT NULL,
  type          TEXT NOT NULL,                    -- 'morning_digest', 'welcome', 'error_alert'
  subject       TEXT,
  status        TEXT DEFAULT 'pending',           -- 'pending', 'sent', 'failed'
  error_message TEXT,
  sent_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- PIPELINE_STATUS TABLE
-- Daily pipeline run health tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_status (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_date            DATE DEFAULT CURRENT_DATE,
  user_id             UUID REFERENCES users(id) ON DELETE SET NULL,  -- NULL = global run

  -- Step completion flags
  step_jobs_fetched   BOOLEAN DEFAULT FALSE,
  step_jobs_matched   BOOLEAN DEFAULT FALSE,
  step_ai_generated   BOOLEAN DEFAULT FALSE,
  step_pdfs_created   BOOLEAN DEFAULT FALSE,
  step_email_sent     BOOLEAN DEFAULT FALSE,

  -- Stats
  jobs_fetched        INTEGER DEFAULT 0,
  jobs_matched        INTEGER DEFAULT 0,
  resumes_generated   INTEGER DEFAULT 0,
  pdfs_generated      INTEGER DEFAULT 0,
  ai_tokens_used      INTEGER DEFAULT 0,
  duration_seconds    FLOAT,

  -- Overall
  status              TEXT DEFAULT 'running',     -- 'running', 'completed', 'failed'
  error_log           TEXT,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  completed_at        TIMESTAMPTZ
);

-- ============================================================
-- API_USAGE TABLE
-- Tracks daily call counts per external API (Adzuna, JSearch,
-- Gemini, OpenAI, Resend) so the pipeline can enforce free-tier /
-- spend budgets across runs. See backend/core/usage_guard.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS api_usage (
  service     TEXT NOT NULL,
  usage_date  DATE NOT NULL DEFAULT CURRENT_DATE,
  count       INTEGER NOT NULL DEFAULT 0,
  updated_at  TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (service, usage_date)
);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- Each user can only access their own data
-- ============================================================
ALTER TABLE users         ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_jobs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_logs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_usage     ENABLE ROW LEVEL SECURITY;
-- No policies defined for api_usage — only the backend's service_role
-- key (which bypasses RLS) should ever read or write it.

-- Users can only read/update their own profile
CREATE POLICY "users_own_profile" ON users
  FOR ALL USING (auth.uid() = id);

-- Users can only see their own matched jobs
CREATE POLICY "user_jobs_own_data" ON user_jobs
  FOR ALL USING (auth.uid() = user_id);

-- Users can only see their own email logs
CREATE POLICY "email_logs_own_data" ON email_logs
  FOR ALL USING (auth.uid() = user_id);

-- Pipeline status is readable by the owner
CREATE POLICY "pipeline_status_own_data" ON pipeline_status
  FOR ALL USING (auth.uid() = user_id OR user_id IS NULL);

-- Jobs table is publicly readable (no RLS — shared data)
-- Backend writes to jobs using service_role key which bypasses RLS

-- ============================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================

-- Auto-update updated_at on row changes
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER user_jobs_updated_at
  BEFORE UPDATE ON user_jobs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
