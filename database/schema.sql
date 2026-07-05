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

  -- Contact / basic info
  phone               TEXT,
  location            TEXT,                        -- user's own current location (free text)

  -- Job preferences
  job_category        TEXT,                        -- e.g. 'ui_ux_designer', 'backend_developer', or free text via search
  target_roles        TEXT[] DEFAULT '{}',        -- e.g. ['UI/UX Designer', 'Product Designer']
  tools                TEXT[] DEFAULT '{}',         -- e.g. ['Figma', 'React']
  skills               TEXT[] DEFAULT '{}',         -- e.g. ['Prototyping', 'REST API Design']
  work_type            TEXT[] DEFAULT '{}',         -- e.g. ['Remote', 'Hybrid']
  experience_level    TEXT DEFAULT 'mid',          -- 'entry', 'mid', 'senior', 'lead'
  preferred_locations TEXT[] DEFAULT '{}',         -- e.g. ['Mumbai', 'Remote', 'Bangalore']
  salary_min          INTEGER,                     -- in INR/month or USD/year
  salary_max          INTEGER,
  remote_preference   TEXT DEFAULT 'any',          -- 'remote', 'hybrid', 'onsite', 'any'

  -- Resume data
  summary              TEXT,                        -- short professional summary
  work_experience       JSONB DEFAULT '[]'::jsonb,   -- [{title, company, start_date, end_date, is_current, bullets:[]}]
  projects              JSONB DEFAULT '[]'::jsonb,   -- [{name, project_type, role, description, technologies:[], url, github}] — NOT work experience
  education             JSONB DEFAULT '[]'::jsonb,   -- [{school, degree, field_of_study, start_date, end_date}]
  resume_text         TEXT,                        -- flattened plain-text resume — kept in sync from structured
                                                     -- data on save so matcher.py / optimizer.py need no changes
  resume_embedding    vector(768),                 -- for matching
  resume_file_path    TEXT,                        -- path in the private "resume-uploads" Storage bucket (not a public URL)
  resume_template     TEXT DEFAULT 'professional', -- PDF design: 'professional' | 'modern' | 'classic' | 'minimal' (backend/templates/)
  confidence_flags     JSONB DEFAULT '{}'::jsonb,    -- e.g. {"phone": "missing", "summary": "low_confidence"}

  -- Profile links
  linkedin_url        TEXT,
  portfolio_url       TEXT,
  github_url          TEXT,

  -- Account settings
  tier                TEXT DEFAULT 'free',         -- 'free', 'pro', 'enterprise'
  is_active           BOOLEAN DEFAULT TRUE,        -- gates matching/pipeline eligibility
  is_subscribed       BOOLEAN DEFAULT TRUE,        -- gates EMAIL only — unsubscribing must not silently stop matching
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
  search_category     TEXT,                        -- job_category this was fetched for (core/matcher.py category gate)

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
  pdf_error_message       TEXT,                    -- set (with status='pdf_failed') when PDF generation fails; cleared on success

  -- Status tracking
  status                  TEXT DEFAULT 'matched',  -- 'matched', 'resume_ready', 'pdf_ready', 'pdf_failed', 'emailed', 'applied', 'interviewing', 'offered', 'rejected'
  applied_at              TIMESTAMPTZ,

  -- Apply-link click tracking (GET /r/{id} redirect — see
  -- backend/api/routes/redirect.py) — the "Apply link click rate" success metric.
  click_count             INTEGER DEFAULT 0,
  last_clicked_at         TIMESTAMPTZ,

  -- Resume feedback (thumbs up/down on the generated PDF)
  feedback                TEXT,                    -- 'up' | 'down'
  feedback_reason         TEXT,                    -- only meaningful for 'down'; free chip value, not free text
  feedback_at             TIMESTAMPTZ,

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
-- RESUME_PARSE_JOBS TABLE
-- Background job status for resume upload -> AI extraction.
-- No user_id: uploads happen during onboarding, before a users row
-- exists. The frontend polls status via the backend API only —
-- never queried directly with the anon key.
-- ============================================================
CREATE TABLE IF NOT EXISTS resume_parse_jobs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status        TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'processing', 'done', 'failed'
  source        TEXT NOT NULL,                    -- 'file' | 'url'
  file_path     TEXT,                             -- path in the private "resume-uploads" Storage bucket
  result        JSONB,                            -- parsed structured data once status = 'done'
  error_message TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- FUNNEL_EVENTS TABLE
-- Signup funnel tracking (docs/PRODUCT_STRATEGY_BETA.md success metrics)
-- — how many people started vs. actually finished, not just the finished
-- count the `users` table alone can show. session_id is an anonymous
-- localStorage id, set before a users row exists; user_id is filled in
-- once known. Public POST /api/analytics/track writes here — no PII,
-- fixed allowlist of event names enforced server-side.
-- ============================================================
CREATE TABLE IF NOT EXISTS funnel_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event       TEXT NOT NULL,          -- 'signup_started' | 'profile_review_reached' | 'signup_completed'
  session_id  TEXT,
  user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
  meta        JSONB DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_funnel_events_event ON funnel_events(event);

-- ============================================================
-- STORAGE BUCKETS (created via Supabase Storage API in code, not SQL —
-- see backend/core/resume_parser.py, same pattern as
-- upload_to_supabase_storage() in backend/core/pdf_generator.py)
--
--   "resumes"        — existing, PUBLIC. AI-tailored generated PDFs
--                       (linked from digest emails).
--   "resume-uploads"  — NEW, PRIVATE. Raw user-uploaded resume files.
--                       Contains PII — only the backend's service_role
--                       key may read/write it, never a public URL.
-- ============================================================

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- Each user can only access their own data
-- ============================================================
ALTER TABLE users         ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_jobs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_logs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_usage     ENABLE ROW LEVEL SECURITY;
ALTER TABLE resume_parse_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE funnel_events ENABLE ROW LEVEL SECURITY;
-- No policies defined for api_usage, resume_parse_jobs, or funnel_events
-- — only the backend's service_role key (which bypasses RLS) should ever
-- read or write them.

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

CREATE TRIGGER resume_parse_jobs_updated_at
  BEFORE UPDATE ON resume_parse_jobs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- MIGRATION — run this block if your `users` table already exists
-- (i.e. you ran an earlier version of this schema). CREATE TABLE IF
-- NOT EXISTS above won't retroactively add these columns.
-- ============================================================
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone               TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS location             TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS job_category        TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS tools                TEXT[] DEFAULT '{}';
ALTER TABLE users ADD COLUMN IF NOT EXISTS skills               TEXT[] DEFAULT '{}';
ALTER TABLE users ADD COLUMN IF NOT EXISTS work_type            TEXT[] DEFAULT '{}';
ALTER TABLE users ADD COLUMN IF NOT EXISTS summary              TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS work_experience      JSONB DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS projects             JSONB DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS education            JSONB DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS resume_file_path    TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS resume_template     TEXT DEFAULT 'professional';
ALTER TABLE users ADD COLUMN IF NOT EXISTS confidence_flags     JSONB DEFAULT '{}'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_subscribed        BOOLEAN DEFAULT TRUE;

ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS click_count       INTEGER DEFAULT 0;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS last_clicked_at   TIMESTAMPTZ;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS feedback          TEXT;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS feedback_reason   TEXT;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS feedback_at       TIMESTAMPTZ;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS pdf_error_message TEXT;

-- Which job_category a job was fetched for — core/matcher.py uses this to
-- stop cross-category matches (e.g. a UI/UX Designer job being shown to a
-- Fullstack Developer with a plausible-looking score). Existing rows stay
-- NULL until re-fetched; matcher.py falls back to a text-based relevance
-- check for those.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS search_category TEXT;

CREATE TABLE IF NOT EXISTS funnel_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event       TEXT NOT NULL,
  session_id  TEXT,
  user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
  meta        JSONB DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_funnel_events_event ON funnel_events(event);
ALTER TABLE funnel_events ENABLE ROW LEVEL SECURITY;

-- Race-condition backstop for the once-per-day digest guard (app-level
-- check lives in core/email_sender.py): two overlapping pipeline runs can
-- never both record a 'sent' morning_digest for the same user on the same
-- UTC day.
-- Note the double parens around the cast expression — Postgres requires
-- an index expression (as opposed to a plain column name) to be wrapped
-- in its own parens, so `(x)::date` needs `((x)::date)` here.
CREATE UNIQUE INDEX IF NOT EXISTS email_logs_one_digest_per_day
  ON email_logs (user_id, type, ((sent_at AT TIME ZONE 'utc')::date))
  WHERE status = 'sent';

-- ============================================================
-- KEEP-WARM — primary defense against Render free-tier sleep
-- Render spins the backend down after ~15 idle minutes (~50s cold start
-- for the next visitor). The GitHub Actions pinger proved unreliable:
-- its "*/10" schedule actually fired every 1–3 hours in practice.
-- pg_cron + pg_net (both available on Supabase free tier) ping /health
-- every 5 minutes straight from the database — reliable and $0.
-- Run this block once in the Supabase SQL Editor.
-- ============================================================
create extension if not exists pg_cron;
create extension if not exists pg_net;
select cron.schedule(
  'keep-render-warm',
  '*/5 * * * *',
  $$ select net.http_get('https://ai-career-copilot-api-nyaa.onrender.com/health') $$
);
-- To stop it later: select cron.unschedule('keep-render-warm');
