# How AI Career Copilot Works — explained for non-coders

A plain-language tour of the whole product: what it does, what it's built
from, why each piece was chosen, and how everything fits together. Written
for someone with zero coding background. If you're a new collaborator,
read this before anything else in `docs/`.

---

## 1. What the product does

AI Career Copilot works like a personal recruiter for job seekers:

1. A person uploads their resume once.
2. Every morning, the system finds jobs that match them.
3. An AI "recruiter" reads each job against their resume and says:
   **apply, worth a shot, or skip** — that's the **Fit Check**.
4. For the good ones, it writes a resume tailored to that exact job, as a PDF.
5. It emails them their matches every morning at their chosen time.

The user never operates it. It runs by itself, every day — which is why so
much of the engineering below is about handling problems *automatically*.

---

## 2. The restaurant analogy — how any web app works

Every modern web app has three parts. Think of a restaurant:

| Restaurant | This app | What it is |
|---|---|---|
| **The dining room** | Frontend | What visitors see and touch — pages, buttons |
| **The kitchen** | Backend | Where the real work happens — hidden from customers |
| **The pantry** | Database | Where everything is stored |

A customer (user) sits in the dining room and orders (clicks a button).
The waiter carries the order to the kitchen (the internet carries a
"request"). The kitchen cooks using ingredients from the pantry (the
backend reads/writes the database) and sends the dish back (the
"response"). The customer never sees the kitchen — on purpose.

Everything below fills in *which* dining room, kitchen, and pantry we
chose, and why.

---

## 3. The dining room — Frontend (`frontend/`)

**Built with:** Next.js + React + TypeScript · **Lives on:** Vercel

- **React** builds pages out of reusable "components" — LEGO blocks. The
  dashboard isn't one giant page; it's blocks: `JobCard` (one job),
  `FitCheckModal` (the review popup), `AddJobPanel` (the paste-a-job box).
  Build a block once (like `SaveButton`), snap it in everywhere.
- **Next.js** is the framework around React — it handles which URL shows
  which page and makes pages load fast.
- **TypeScript** is the browser's language (JavaScript) with a
  spell-checker for data. It forces declarations like "a Job has a title,
  a company, a location…" — and if code tries to use a salary as text
  when it's a number, the build **fails before users ever see it**.
  That's why every release runs `npm run build` first.
- **Vercel** hosts these pages and rebuilds the site automatically when
  new code is pushed.

**Why these?** The most common combo in the world — huge community,
everything documented, easy to hire for later.

---

## 4. The kitchen — Backend (`backend/`)

**Built with:** Python + FastAPI · **Lives on:** a Hostinger VPS,
managed by Coolify, packaged with Docker

- **Python** is the kitchen's language — the #1 language for AI work
  (every AI provider ships Python tools first), and it reads almost like
  English.
- **FastAPI** turns Python functions into "endpoints" — order counters.
  `POST /job-intake/extract` is a counter where the frontend hands over
  "here's a job link, read it" and gets structured data back. The app has
  ~40 counters (dashboard data, generate resume, admin tools…). They live
  in `backend/api/routes/`.
- **The VPS** is a rented computer that's always on. **Coolify** is the
  manager living on it: it watches GitHub, and when new code lands on the
  `main` branch, it rebuilds and restarts the kitchen. "Merged to main"
  is what triggers a deploy.
- **Docker** (`backend/Dockerfile`) is a recipe describing the kitchen
  itself — "install Python, install these tools, start the server." It
  guarantees the server's kitchen is *identical* to the one where tests
  passed. (Lesson learned live: the previous build system silently
  skipped installing a library the PDF-maker needed — PDFs crashed in
  production while working everywhere else.)

---

## 5. The pantry — Database (`database/schema.sql`)

**Built with:** Supabase — which is PostgreSQL (the world's most trusted
free database) with a friendly control panel.

A database is a set of spreadsheets that never get lost. The important
"tables":

- **`users`** — one row per person: name, email, skills, resume text.
- **`jobs`** — every job ever fetched: title, company, description,
  required experience.
- **`user_jobs`** — the *connecting* table: "this user matched this job
  on this day." One row carries the match, the Fit Check verdict, the
  tailored resume, the PDF link, applied status, the user's notes,
  saved-for-later. The dashboard mostly reads this table.
- **`email_logs`** — a receipt book for every email sent.

Supabase also stores files (resume PDFs) and does **vector search**: it
converts a resume and a job into lists of numbers ("embeddings") and
measures how similar they are *in meaning*, not just in shared words.

---

## 6. The AI brain — the waterfall (`backend/core/ai.py`)

The app calls AI for: matching, Fit Check verdicts, tailored resumes,
cover letters, and reading job screenshots.

**Problem:** good AI costs money, and the app runs on free tiers. Free
tiers run out — Gemini allows ~20 calls a *day*.

**Solution — the waterfall:** seven providers are configured (Groq →
Gemini → OpenRouter → GitHub Models → Mistral → Cohere → OpenAI). Every
request tries the first; if it's out of quota or down, it slides to the
next automatically, like water down steps. Users never notice a provider
dying.

On top sits the **budget guard** (`backend/core/usage_guard.py`): daily
allowances per provider AND per user (auto resumes, cover letters, Fit
Checks per day). Without it, one person clicking all day could drain the
whole app's AI for everyone.

**House rule:** the AI never shows *invented numbers*. No "73% interview
probability", no "estimated 130 applicants" — no AI actually knows those.
Verdict + written reasons only. One fake number a user catches destroys
their trust in every real one.

---

## 7. Where jobs come from (`backend/jobs/fetchers.py`)

Two free job-listing services: **Adzuna** (primary) and **JSearch**
(supplementary, tiny free tier). Their data is messy — many postings
don't say how much experience they want — so there's a ladder of
increasingly expensive tricks:

1. Free: search the job text for patterns like "2-5 years experience".
2. Free: infer from the title ("Senior…" ≈ 5+ years).
3. Cheap: fetch the job's real application webpage and search that.
4. Last resort: ask an AI to read it — budget-capped.

Users can also bring their own job (link / pasted text / screenshot) via
the Fit Check intake (`backend/core/job_intake.py`) — links are read with
a real headless browser when the simple fetch fails, and screenshots go
through AI vision.

---

## 8. A day in the life of the app

```
2:00 AM — the scheduler (an alarm clock inside the backend) wakes up
   ↓
Fetch fresh jobs from Adzuna/JSearch for every user's category & city
   ↓
Filter: right category? right experience level? not shown before?
   ↓
Match: score each remaining job against each user's resume
   ↓
Fit Check the top matches (AI recruiter reads job vs resume)
   ↓
Generate tailored resumes for the winners → render PDFs → store them
   ↓
7:00 AM (or the user's slot) — email each user their digest
```

Separately, on the dashboard users can act on demand: run a Fit Check,
paste a job they found, generate a resume or cover letter for a specific
match, save jobs for later with personal notes.

---

## 9. How the map fits together

```
        USERS (phone / laptop browser)
                │
    ┌───────────▼───────────┐
    │  FRONTEND — Next.js   │  the dining room (Vercel)
    │  dashboard, Fit Check │
    └───────────┬───────────┘
                │ requests (the waiter)
    ┌───────────▼───────────┐
    │  BACKEND — FastAPI    │  the kitchen (VPS + Coolify + Docker)
    │  matching, scheduler, │
    │  PDF maker, emails    │
    └──┬──────┬──────┬──────┘
       │      │      │
   ┌───▼──┐ ┌─▼───────────┐ ┌▼──────────────┐
   │Supa- │ │ AI waterfall│ │ Job sources    │
   │base  │ │ Groq→Gemini │ │ Adzuna/JSearch │
   │(data)│ │ →5 more     │ │                │
   └──────┘ └─────────────┘ └───────────────┘
       plus: Gmail/Resend (email), GitHub (code home)
```

---

## 10. How the work gets done (the process)

The pattern behind every fix and feature in this project:

1. **A symptom is reported** — usually a founder screenshot ("Kevin sees
   designer jobs", "I get bounce emails daily").
2. **Find the root cause, not the surface.** The daily bounce emails
   looked like a typo'd address; the real cause was a design flaw where
   editing your email silently created a second account. Fix the disease,
   not the symptom.
3. **Write tests** — small robot checkers (`backend/tests/`). This
   project went from 0 to 118 automatic tests. Every release re-runs all
   of them in seconds, so changing code can't silently re-break last
   month's fixes.
4. **Ship in small rounds** — commit → push → merge to `main` → Coolify
   deploys. Small steps mean when something breaks, you know which step
   broke it.
5. **Build admin tools for self-diagnosis** — the AI provider tester, the
   suspect-email scanner, the PDF failure list (all in the `/admin`
   panel). A founder who can diagnose without a developer moves 10× faster.

**The one-line summary:** software isn't built, it's *grown* — symptom,
root cause, fix, test, ship, repeat.
