# AI Career Copilot

> Wake up to 3 tailored jobs with AI-optimized resumes every morning.

**Author:** Gargey Patel | gargeypatel123@gmail.com
**Status:** Active Development (v2.0)

---

## Quick Start (Local Development)

### 1. Start local database & Redis
```bash
cd docker
docker-compose up -d
```

### 2. Set up backend
```bash
cd backend
python -m venv venv && source venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
```

### 3. Run database schema
Go to Supabase Dashboard → SQL Editor → Paste contents of `database/schema.sql` → Run

**Also run the pgvector match function** — copy it from:
```bash
python backend/core/matcher.py
```

### 4. Test the backend
```bash
cd backend

# Test DB connection
python database/supabase_client.py

# Test job fetching
python jobs/fetchers.py

# Test AI provider
python core/ai.py

# Run full pipeline (test mode)
python pipeline.py --test
```

### 5. Start API server
```bash
cd backend
uvicorn api.main:app --reload
# API docs: http://localhost:8000/docs
```

### 6. Set up frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local   # fill in Supabase keys
npm run dev
# Open: http://localhost:3000
```

---

## Deploy (Free Tier)

### Backend → Render
1. Push this repo to GitHub, then in Render click **New → Blueprint** and point it at the repo — it reads `render.yaml` at the repo root automatically.
2. In the service's **Environment** tab, fill in the vars marked `sync: false` (Supabase keys, AI provider keys, etc. — see `backend/.env.example`). `FRONTEND_URL` should be your Vercel URL once you have it (step below).
3. Render gives you a URL like `https://ai-career-copilot-api.onrender.com`. Free tier sleeps after 15 min idle — the first request after that takes ~30-60s to wake up.

### Frontend → Vercel
1. Import the repo in Vercel and set **Root Directory** to `frontend` (Project Settings → General — required since this is a monorepo).
2. Add env vars from `frontend/.env.local.example`, setting `NEXT_PUBLIC_API_URL` to your Render URL from above.
3. Deploy. Once you have the Vercel URL, set it as `FRONTEND_URL` on the Render backend so CORS allows requests from it.

---

## Documentation
- [Product Requirements](docs/PRD.md)
- [Technical Architecture](docs/TECH.md)
- [API Keys Setup Guide](Try%20auto%20Job/README.md)

---

## Project Structure
```
ai-career-copilot/
├── docs/                   ← PRD, TECH, guides
├── database/               ← SQL schema, migrations
├── docker/                 ← Docker Compose (local DB + Redis)
├── backend/
│   ├── api/                ← FastAPI routes
│   ├── core/               ← AI, Matcher, Optimizer, PDF, Email
│   ├── jobs/               ← Job fetchers (Adzuna, JSearch)
│   ├── database/           ← Supabase client
│   └── pipeline.py         ← Main daily runner
└── frontend/               ← Next.js app
```

---

## Cost at Scale
| Users | Est. AI Cost/Day |
|-------|-----------------|
| 10    | ₹0 (free tier) |
| 100   | ~₹3/day |
| 1000  | ~₹30/day |
| 10000 | ~₹300/day |
