# AI Career Copilot — Product Strategy (Beta)

**Version:** 2.1 Beta
**Status:** Active — this is the source of truth for all product decisions during beta
**Owner:** Gargey Patel
**Last Updated:** July 2026

Every AI coding assistant (Claude, GPT, Cursor, Codex, …) must read this document
before making product decisions. When a decision here conflicts with an older
document or an assistant's instinct, this document wins.

---

## Vision

AI Career Copilot is an AI-powered career operating system. Our mission is to help
people spend less time searching for jobs and more time applying to the right
opportunities.

We are not building another job board. We are building an intelligent application
assistant.

## North Star

> Help anyone, in any profession, go from **"I need a job."** to
> **"I've already applied."** in the shortest amount of time possible.

Every product decision should support this goal.

---

## Product Philosophy

We are NOT building: LinkedIn, Indeed, Naukri, another resume builder, another
resume checker.

We ARE building an assistant that helps users find better jobs, match the right
jobs, tailor resumes, generate application materials, and apply faster.

---

## Product Values

1. **Trust** — Never fake statistics. Never invent experience. Never promise
   interviews or offers. Only display information we actually know. This applies
   to marketing copy too: no invented user counts, job counts, or urgency.
2. **Transparency** — Users should always know why a job matched, what AI
   changed, and which resume was generated.
3. **Automation** — Reduce work; never create more work.
4. **Encouragement** — Never punish or block users for an incomplete profile.
   Coach, guide, encourage.
5. **Flexibility** — Support every profession. Nothing hardcoded for one field.
6. **Scalability** — New professions are added with data and configuration, not
   by rewriting application logic.
7. **Cost discipline** — Beta runs at ~$0. Every AI feature must fit inside the
   daily API budget caps (see `backend/core/config.py`), and must degrade
   gracefully when a cap is hit (e.g. vector matching falls back to keyword
   matching). A feature that only works with paid quota is a post-beta feature.

---

## Target Audience vs. Beta Cohort

**The platform** is built for everyone. It supports career *domains* (Technology,
Design, Marketing, Sales, Finance, HR, Healthcare, Education, Customer Support,
Operations, Legal, Manufacturing, Hospitality, Government, Students & Freshers),
each containing many roles. Nothing in the codebase may assume one profession.

**The beta cohort** is deliberately narrow: **Design + Technology candidates and
students/freshers in India** — the audience the founder can personally recruit
and talk to. ~100 users in 1–2 domains produces real learning; 100 users across
15 domains produces noise. We validate deep, then widen.

## Architecture Philosophy

Career Domain → Specific Role → Skills → Resume → AI Matching →
Resume Optimization → Application. The same platform supports thousands of
professions through this chain.

---

## Beta Goals

Beta is NOT for revenue. Beta is for validation. We need to answer: Will users
upload resumes? Trust AI? Return every morning? Open daily emails? Download
optimized resumes? Apply through the platform? If yes, we continue building.

## Core User Journey

Landing Page → Get Started → Upload Resume → AI Resume Parsing → Review
Information → Complete Profile → **Instant First Matches** → Daily Job Matching →
Resume Optimization → Morning Email → Apply → Dashboard Stores History

**Instant First Matches is a core journey step, not an experiment.** Signup must
end with "here are your first matches", never with an empty dashboard and "come
back tomorrow". The first session is where trust is won or lost.

## Authentication (decision recorded July 2026)

**No login wall during beta.** Accounts are identified by a private dashboard
link (unguessable UUID) plus browser memory for returning visitors. This honors
the friction rule (only name + email required) and ships faster. Full
authentication (magic-link email login, then optional password/OAuth) is in
`POST_BETA_ROADMAP.md`. Copy must be honest about this model: "your private
dashboard link", never "your account is secured".

---

## Onboarding Strategy

Everything except **Name** and **Email** is optional. Never block onboarding.
Encourage users to improve their profile instead.

### Profile Completion Philosophy

Never display "Required" (except name/email). Display **"Recommended"** with a
reason WHY. Rendered with a Lucide sparkle icon — never emoji characters (design
system rule).

Encouragement copy per section:

- **Resume** — Uploading a resume allows AI to tailor every application
  automatically.
- **Experience** — Internships, freelance work and part-time jobs all improve
  matching quality.
- **Projects** — Projects showcase practical skills and are especially valuable
  for students and early-career professionals.
- **Skills** — Skills help AI understand which opportunities best match your
  background.
- **Education** — Education provides additional context for more accurate
  recommendations.
- **Portfolio** — A portfolio helps recruiters better understand your work.
  Don't have one? No problem — you can always add one later.
- **LinkedIn** — Gives recruiters another way to learn about your experience.

### Profile Strength

Show progress, not errors: a percentage plus Completed (✓) and Pending (○)
lists. The goal is motivation, not punishment.

---

## Resume Strategy

Every user has: Original Resume → AI Parsed Resume → Resume History → Optimized
Resume. Users can always view, download, and replace their original resume.
Transparency builds trust.

## Projects

Projects are NOT work experience; they get their own section. Types: Personal,
Academic, Freelance, Research, Open Source, Capstone. Fields: name, role,
description, technologies, project URL, GitHub, optional images (future). The
parser should detect projects automatically; users can move items between
Projects and Experience.

## Experience

Professional work only: full-time, part-time, freelance, internships. Projects
are never stored here.

## Portfolio

Optional; never blocks anything. Future: portfolio builder, Behance / Dribbble /
GitHub / Figma import.

---

## Job Collection Strategy

Never depend on one source. Sources → Normalizer → Central Job Database →
Matching Engine → Resume Engine → Dashboard → Morning Email.

Current live sources: Remotive, Greenhouse boards, Jobicy (free), plus Adzuna
and JSearch when API keys are configured. Aspirational sources (LinkedIn,
Indeed, Wellfound, company pages, government portals) belong in the roadmap —
marketing copy may only name sources we actually fetch from.

## AI Matching

Current: keyword matching + AI analysis (vector matching where available, with
keyword fallback). Future: richer embeddings, preference learning, behavior
learning.

---

## Dashboard Philosophy

The dashboard is a **workspace, not another job board**. It contains: Today's
Matches, Resume Ready, Pipeline Status, Recent Digests, Resume History, Profile
Strength, Settings. No endless scrolling feed.

### Dashboard Metrics (Beta)

Display only real information.

**Allowed:** Jobs Found, Resume Generated / Resume Ready, Profile Strength,
Last Pipeline Run, Pipeline Status.

**Do NOT display:** Applications, Interviews, Offers — until the platform can
actually verify them. (Interview tracking is post-beta; see roadmap.)

## Email Philosophy

Email is the daily action; the dashboard is the archive. Every morning: top
matches → optimized resume → (future: cover letter) → apply link → open
dashboard. The email answers "What should I apply to today?"

Until email sending is live and verified, no user-facing copy may promise a
morning email or a delivery time. Promise the dashboard instead.

---

## Data Privacy (Trust in practice)

A resume is the most sensitive document a job seeker owns.

- Resumes are stored in a **private** storage bucket; generated PDFs the user
  requests are the only public artifacts.
- User data is never sold or shared with third parties.
- AI processes a user's data only to serve that same user's applications.
- Users can request deletion of their account and all data at any time
  (founder email during beta; self-serve post-beta).
- Relevant law: India's DPDP Act. Keep this section honest as the product grows.

---

## Resume Templates

Beta: Modern, Classic, Minimal (live). Future: Creative, Executive, ATS Ultra,
Academic.

## Beta Scope

**Included:** Landing page, private dashboard links (see Authentication),
resume upload, AI resume parsing, projects, experience, education, skills,
portfolio links, dashboard, resume templates, daily matching, instant first
match, resume optimization, morning email, resume download.

**Not included** (see `POST_BETA_ROADMAP.md`): full authentication, interview
tracking, offer tracking, salary insights, Chrome extension, portfolio builder,
premium plans, analytics, recruiter portal, team accounts, dark mode, themes,
AI chat assistant.

---

## Success Metrics

Track weekly. A target without a measurement method is not a target.

| Metric | Target | How we measure |
|---|---|---|
| Total signups | 100 | Admin overview (`/admin`) — live |
| Resume upload rate | 80% | Admin overview `has_resume` — live |
| Profile completion | 70% | Profile Strength avg — build with Profile Strength |
| Daily email open rate | 60% | Resend webhooks — build with email (Phase 3) |
| Resume download rate | 50% | Download click tracking — build with PDF delivery |
| Apply link click rate | 40% | Backend redirect links (`/api/r/...`) — required build; direct outbound links are unmeasurable |
| Returning users | 30% | Dashboard visit logging — small backend counter |

Ignore vanity metrics.

---

## Product Principles

Every feature must answer: **Does this reduce the time between "I need a job"
and "I submitted an application"?** If NO, it goes to `POST_BETA_ROADMAP.md`,
not into the beta.

Three questions before building anything new:
1. Does it help users apply faster?
2. Can we actually support it with real data?
3. Is it essential for beta, or can it wait until we validate the product?

## Long-Term Vision

Today: AI Career Copilot finds jobs. Tomorrow: it manages the complete career
journey. Future modules: Interview Coach, Portfolio Builder, Application
Tracker, Career Analytics, Salary Insights, Personal Website Builder, Recruiter
CRM, Chrome Extension, AI Career Agent.

## Final Principle

We are not building another place to search for jobs. We are building the
fastest and smartest way for anyone, in any profession, to move from
discovering an opportunity to submitting a high-quality application. Every
design, engineering, and product decision should support that mission.
