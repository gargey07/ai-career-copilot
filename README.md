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
