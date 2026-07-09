# Project Audit — AI Career Copilot

**Date:** July 2026 · **Scope:** full codebase (backend, frontend, database, deploy config)
**Live:** Render (FastAPI backend, free tier) + Vercel (Next.js frontend) + Supabase (Postgres/pgvector/Storage)

This is the honest state of the system: what works, what broke and why, what was
fixed in this audit, and what to build next. Companion docs:
`PRODUCT_STRATEGY_BETA.md` (product rules), `AI_CAREER_INTELLIGENCE_ENGINE.md`
(pipeline failure-mode contract), `POST_BETA_ROADMAP.md`.

---

## 1. Architecture (as actually deployed)

```
Signup (Next.js) ──► POST /api/resumes/confirm ──► instant background task:
                                                    fetch user's category → match → resumes → PDFs

Daily (in-process scheduler, api/main.py):
  first due slot → fetch (2 queries/category, tagged) → embed → match all users
  each user's slot (preferred_digest_time, IST) → resumes → PDFs → digest email
  every tick → retry today's failed digests (max 3/user/day)

AI text generation: Groq → Gemini → OpenRouter → GitHub Models → Mistral → Cohere → OpenAI
  (waterfall; any configured key joins the chain; embeddings always Gemini)
Email: Gmail SMTP (port 465 → 587 fallback, IPv4-only) → Resend
  (true failover; every attempt logged to email_logs; admin alert on failure)
PDF: Playwright Chromium (60s cap, one-at-a-time lock, self-installs at boot)
Keep-warm: Supabase pg_cron pings /health every 5 min (GitHub Actions = backup only)
```

## 2. Bugs found in THIS audit (both fixed, with regression tests)

| # | Bug | Impact | Fix |
|---|-----|--------|-----|
| 1 | `store_matches` early-returned on an empty fresh ranking **before** the stale-row cleanup ran | The exact "Himanshu still sees UI/UX jobs" case: when the corrected category filter finds zero relevant jobs, the wrong rows from an earlier buggy run could never be cleaned by re-running the pipeline | Cleanup moved above the early return — an empty corrected ranking now still removes unprogressed stale rows (`core/matcher.py`) |
| 2 | Instant-first-match only searched the existing job pool | A signup in a never-before-fetched category (first fullstack dev, first marketer…) got an empty dashboard until the next morning — breaking the "signup ends with real matches" core promise (worse now that category filtering removed the old junk-padding that used to mask it) | `_match_new_user` now fetches jobs for the new user's category (1 query, budget-guarded, category-tagged) before matching (`api/routes/resumes.py`) |

## 3. Recently fixed (earlier sessions, verified still in place)

- **7930% match scores** — 0–1 vs 0–100 scale collision; normalized at storage + every display site.
- **Resume PDF quality** — strict pipe-format AI output + hardened parser; watermark removed; "Professional" (Jake's-Resume-style) template added and made default.
- **"Resumes Ready: 0" lock** — optimizer/PDF select by work-remaining, not exact status.
- **Email `[Errno 101]`** — IPv4-only SMTP + port 587 STARTTLS fallback + true Gmail→Resend failover + same-day retries + admin alerts.
- **Cross-category matches** — `search_category` tag at fetch, category gate on both matching paths, no cross-category backfill, 0.55 keyword floor, same-day stale-row self-healing.
- **Manual pipeline clicking** — in-process daily scheduler with per-user digest slots (IST) and DB day-locks.
- **Missing Chromium** — self-heals at boot; loud build-log warning on install failure.
- **AI cost/latency** — Groq-first waterfall (Gemini's real free quota is 20/day), 7-day resume reuse cache, cover letters off by default.

## 4. Known limitations (accepted for beta — revisit before public launch)

1. **No auth on dashboards** — anyone with a `user_id` link sees that dashboard.
   The single biggest pre-launch blocker. Needs Supabase Auth / magic-link sessions.
2. **Admin token in query params** — appears in server/request logs. Move to an
   `Authorization` header when touching admin next.
3. **Resend can only deliver to the founder's address** until a domain is verified —
   if Gmail is fully down, other users' digests fail (visible in Recent emails +
   alert). Options: verify a domain on Resend, or add Brevo (free 300/day HTTP API).
4. **Render free tier** — 0.1 CPU / 512MB / spins down when keep-warm lapses; PDF
   renders are serialized; cold start ~50s. Fine at beta scale, first paid upgrade
   when real users arrive.
5. **Match scores are not calibrated** — keyword scores are a heuristic; the score
   *breakdown* feature (T-007) stays deferred until scores mean something, per the
   no-fabricated-numbers rule.
6. **Legacy jobs have no `search_category`** — covered by a text-relevance fallback;
   precision improves automatically as fresh tagged fetches replace the old pool
   (7-day freshness window).

## 5. Feature roadmap (recommended order)

**Now / next sprint**
1. **Dashboard auth** (magic link via Supabase Auth) — pre-launch blocker, see §4.1.
2. **"I applied" button on job cards** — user-asserted application tracking; the
   honest version of the Applications metric, feeds funnel + future personalization.
3. **Email deliverability** — verify a custom domain (Resend or Gmail alias),
   SPF/DKIM; removes the single-provider dependency and the ~500/day Gmail ceiling.

**Soon**
4. **Feedback-driven matching** — thumbs-down reasons (already collected) demote
   similar jobs/companies for that user; first real personalization loop.
5. **Match-score calibration + breakdown (T-007)** — once vector matching covers
   most jobs, show Skills/Experience/Role component scores derived from real data.
6. **Admin: quota overrides + job search by title (T-023), signed-URL resume
   viewing + audit log (T-016)** — operational conveniences as user count grows.

**Later**
7. Soft-delete with 30-day recovery (T-011) — once there are real users worth recovering.
8. Weekly summary email ("your week: X matches, Y resumes, Z clicks").
9. Multi-region job sources (currently India-centric Adzuna + global boards).
10. Interview-prep content per match (JD-derived questions) — new AI surface, cost-gated.

## 6. Operations runbook (quick reference)

- **Pipeline didn't run?** `/admin` → API usage (did `daily_pipeline` consume?) →
  Render logs for `⏰ Scheduler:` lines. Manual: "Run pipeline now".
- **Emails failing?** `/admin` → Recent emails (status + error). Gmail auth errors →
  regenerate the app password; network errors → check Render status; alerts also
  land in the founder inbox (cap 5/day).
- **PDFs failing?** Inspect view shows `pdf_error_message`; "Executable doesn't
  exist" → wait for boot self-install or clear-cache redeploy.
- **Wrong/stale matches today?** Re-run the pipeline — unprogressed stale rows
  self-clean. Rows with generated resumes attached are never auto-deleted
  (delete today's rows manually in SQL if truly needed, then re-run).
- **All SQL migrations** live in `database/schema.sql` (idempotent blocks at the
  bottom); pg_cron keep-warm block is documented there too.
