# Technical Architecture Document
# AI Career Copilot — v2.0

**Author:** Gargey Patel
**Last Updated:** 2026-06-29

---

## 1. High-Level Architecture

```
[Scheduler (APScheduler)]
         │
         ▼
[Job Collection Workers]   ← Adzuna, JSearch, Remotive, Wellfound
         │
         ▼
[Normalization + Dedup]
         │
         ▼
[PostgreSQL + pgvector]    ← Central Job Store
         │
         ▼
[Matching Engine]          ← Cosine similarity, no AI here
         │
         ▼
[Redis Queue (RQ)]         ← Async processing
         │
         ▼
[AI Workers]               ← Resume + Cover Letter (Gemini)
         │
         ▼
[PDF Worker]               ← Playwright HTML → PDF
         │
         ▼
[Storage Worker]           ← Upload to Cloudflare R2
         │
         ▼
[Email Worker]             ← SMTP / Resend
         │
         ▼
[User Dashboard]           ← Next.js frontend
```

---

## 2. Technology Stack

### Frontend
| Component | Technology |
|-----------|-----------|
| Framework | Next.js 14 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS |
| Auth | NextAuth.js (Google OAuth + Email) |
| State | React Context + SWR |
| Hosting | Vercel |

### Backend
| Component | Technology |
|-----------|-----------|
| Framework | FastAPI (Python 3.11+) |
| Language | Python |
| Auth | JWT + Supabase Auth |
| Task Queue | RQ (Redis Queue) |
| Scheduler | APScheduler |
| ORM | SQLAlchemy (async) |
| Hosting | Railway / Render |

### Database
| Component | Technology |
|-----------|-----------|
| Primary DB | PostgreSQL (Supabase hosted) |
| Vector Search | pgvector extension |
| Caching | Redis |
| File Storage | Cloudflare R2 (S3-compatible) |

### AI
| Component | Technology |
|-----------|-----------|
| Primary Model | Gemini 1.5 Flash (free tier first) |
| Interface | Abstracted AI class (swappable) |
| Embeddings | Gemini Embedding Model / sentence-transformers |
| Fallback | OpenAI GPT-4o-mini |

### PDF Generation
| Component | Technology |
|-----------|-----------|
| Renderer | Playwright (headless Chromium) |
| Templates | HTML + Tailwind CSS |
| Output | PDF binary → Cloudflare R2 |

### Email
| Component | Technology |
|-----------|-----------|
| Primary | Resend (developer-friendly SMTP API) |
| Fallback | Gmail SMTP / Amazon SES |
| Templates | React Email (JSX email templates) |

---

## 3. Database Schema

### `users`
Stores registered users and their profile preferences.
```sql
id, email, name, avatar_url, google_id,
target_roles, experience_level, preferred_locations,
salary_min, salary_max, remote_preference,
resume_text, linkedin_url, portfolio_url,
tier, is_active, timezone, created_at
```

### `jobs`
Central job store — shared across all users.
```sql
id, source, external_id, title, company, location,
description, url, salary_min, salary_max, employment_type,
seniority_level, is_remote, company_email, career_page_url,
embedding (vector), posted_at, collected_at, expires_at
```

### `user_jobs`
Tracks which jobs were matched and processed for each user.
```sql
id, user_id, job_id, match_score,
optimized_resume_text, cover_letter_text,
pdf_url, status, applied_at, created_at
```

### `email_logs`
Tracks all outgoing emails.
```sql
id, user_id, type, subject, status, sent_at, error_message
```

### `pipeline_status`
Daily pipeline health per user.
```sql
id, user_id, date, jobs_fetched, jobs_matched,
resumes_generated, pdfs_generated, email_sent,
ai_tokens_used, duration_seconds, status, error_log
```

---

## 4. API Design

### Auth Endpoints
```
POST /api/auth/register
POST /api/auth/login
POST /api/auth/google
POST /api/auth/logout
GET  /api/auth/me
```

### User Endpoints
```
GET  /api/users/profile
PUT  /api/users/profile
POST /api/users/resume
GET  /api/users/preferences
PUT  /api/users/preferences
```

### Jobs Endpoints
```
GET  /api/jobs/today          ← Today's matched jobs
GET  /api/jobs/{id}
GET  /api/jobs/search?q=
```

### Resume Endpoints
```
GET  /api/resumes             ← All generated resumes
GET  /api/resumes/{id}
GET  /api/resumes/{id}/pdf    ← Download PDF
POST /api/resumes/generate    ← Manual trigger
```

### Pipeline Endpoints (Admin)
```
GET  /api/admin/pipeline/status
POST /api/admin/pipeline/trigger
GET  /api/admin/users
GET  /api/admin/analytics
```

---

## 5. Cost Optimization Strategy

### Rule 1: One Scheduler, Not N Schedulers
One hourly job fetch runs for ALL users. Jobs are stored centrally.

### Rule 2: Match Before AI
Vector similarity ranking happens in PostgreSQL — no LLM cost.
AI is only invoked for the **Top 3 jobs per user**.

### Rule 3: Cache Everything
- Job descriptions → cached after first embedding
- Company info → cached per company
- AI-generated content → stored in DB, never re-generated unless job changes

### Rule 4: Use Cheapest Viable Model
- Gemini 1.5 Flash: free tier (1500 req/day), costs ~$0.075/1M tokens paid
- Embeddings: sentence-transformers locally (zero cost)

### Cost Estimate at Scale
```
100 users × 3 resumes/day = 300 AI calls/day
300 × ~1500 tokens avg = 450,000 tokens/day
Gemini Flash cost: ~$0.034/day for 100 users
= ₹2.85/day total or ₹0.028/user/day
```

---

## 6. Scalability Plan

| Scale | Strategy |
|-------|----------|
| 5–50 users | Single server, laptop/Railway, SQLite for dev |
| 50–500 users | Supabase Pro, Railway, Redis |
| 500–5000 users | Supabase + dedicated Redis, multiple RQ workers |
| 5000+ users | Kubernetes, multi-region, separate read replicas |

---

## 7. Security

- All secrets stored in environment variables (never hardcoded)
- Service-role Supabase key used only in backend (never exposed to frontend)
- Row Level Security (RLS) enabled on all Supabase tables
- JWT tokens expire in 24 hours (refresh token for 30 days)
- All user data isolated — users can only access their own records
- PDF links are signed (time-limited URLs from R2/S3)

---

## 8. AI Abstraction Layer

All AI calls go through a single `AIProvider` interface. This ensures we can swap Gemini for OpenAI or Claude in one place without changing any business logic.

```python
# backend/core/ai.py (interface)

class AIProvider(ABC):
    async def generate_text(self, prompt: str) -> str: ...
    async def embed_text(self, text: str) -> list[float]: ...

class GeminiProvider(AIProvider): ...
class OpenAIProvider(AIProvider): ...
class ClaudeProvider(AIProvider): ...
```

---

## 9. Local Development Setup

```bash
# 1. Clone repo
git clone https://github.com/yourusername/ai-career-copilot
cd ai-career-copilot

# 2. Start local services (Postgres + Redis)
docker-compose up -d

# 3. Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
python -m uvicorn api.main:app --reload

# 4. Frontend
cd ../frontend
npm install
cp .env.local.example .env.local   # fill in your keys
npm run dev
```
