# AI Career Copilot — Beta Product Log

**Version:** 1.1
**Status:** Active
**Owner:** Gargey Patel

## Purpose

This document records everything learned during the beta. It is the single
source of truth for product improvements before public launch. Every decision
should be based on real user feedback instead of assumptions.

## Beta Goals

The purpose of beta is NOT to build more features — it is to learn:
Do users understand the product? Upload their resume? Complete their profile?
Trust AI-generated resumes? Open the daily email? Apply to jobs? Return the
next day?

## Success Metrics

Targets and measurement methods live in `PRODUCT_STRATEGY_BETA.md` (Success
Metrics table). Update the "Current" numbers here weekly from `/admin`.

| Metric | Target | Current |
|---|---|---|
| Total signups | 100 | |
| Resume upload rate | 80% | |
| Profile completion | 70% | |
| Daily email open rate | 60% | |
| Resume download rate | 50% | |
| Apply link click rate | 40% | |
| Returning users | 30% | |

---

## User Feedback

Format — Date / User / Feedback / Priority / Decision / Status.

*(Log entries here as beta users report things.)*

---

## UX Improvements

### Pending
- Make onboarding feel shorter.
- Add Profile Strength.
- Improve dashboard empty state further (first-run experience).
- Explain AI resume changes (Change Report — with Phase 3).
- Better mobile spacing.
- Projects section (separate from Experience).

### Completed
- Light theme + design system (docs/design-system.md).
- Lucide icons everywhere (no emojis).
- Resume templates (Modern / Classic / Minimal) with visual picker.
- Better review page (ProfileEditor).
- Improved experience cards + month/year pickers.
- Loading states everywhere (skeletons, not spinners).
- Returning-user routing (logo/nav → dashboard).
- Keep-warm pings (Render cold-start mitigation).
- Founder admin view (/admin: users funnel + API budgets).
- Trust-alignment pass: no fake stats, no unverifiable dashboard metrics,
  no internal implementation names in copy.
- Instant first match after signup confirm.

---

## Product Decisions (confirmed)

- Dashboard is a workspace, not another job board.
- Email is the primary daily experience (once live); dashboard is the archive.
- Projects are separate from Experience.
- Everything except Name and Email is optional.
- AI never invents information.
- Resume optimization must be transparent.
- Resume history will be stored.
- Profile completion uses encouragement ("Recommended" + why), not warnings.
- No login wall during beta — private dashboard links + browser memory; real
  auth is post-beta (decision July 2026).
- Beta cohort: Design + Tech candidates and students/freshers in India; the
  platform itself stays profession-agnostic.

## Current Known Problems

- Empty dashboard before the first pipeline run (mitigated by instant first
  match; still weak if the job pool is empty).
- Users don't yet see what AI changes (Change Report not built).
- Resume upload benefits not obvious at the upload step.
- Long onboarding may reduce completion (Profile Strength should help).
- Email delivery not live yet (Resend unverified) — the "morning" promise
  currently lives on the dashboard only.

## Bugs

### High priority
- *(none logged)*

### Medium priority
- *(none logged)*

### Low priority
- *(none logged)*

---

## Feature Requests (frequently requested)

Cover Letter Generator · Interview Preparation · Portfolio Builder · LinkedIn
Optimizer · Chrome Extension · One-Click Apply · Resume Version Comparison

## Product Experiments

1. **Profile Strength** — hypothesis: users complete more sections. Result: pending.
2. **Explain AI resume changes** — hypothesis: users trust AI more. Result: pending.
3. **Instant first match after signup** — hypothesis: users understand product
   value immediately. Status: shipped as a core journey step; measure day-1
   return rate.

## Competitor Notes

- **LinkedIn** — huge job database / manual applications → automate everything
  after discovery.
- **Teal** — good tracking / limited AI transparency → show the AI change report.
- **Jobscan** — good ATS analysis / no application workflow → integrate ATS
  analysis into the full pipeline.

## Beta Learnings

*(Record discoveries here, e.g. "Users care more about WHY the AI changed the
resume than about receiving another PDF.")*

## Ideas Parking Lot

Moved to `POST_BETA_ROADMAP.md` — the single parking lot. Do not build parked
ideas during beta.

## Weekly Review (every Friday)

- What did users love?
- What confused users?
- What should we improve next week?
- What should we NOT build yet?

## Product Principles

Whenever a new idea comes up, ask:
1. Does it reduce the time between discovering a job and applying?
2. Can we support it with real data?
3. Will it help beta users immediately?

If any answer is "No" → `POST_BETA_ROADMAP.md`.

## Final Reminder

Beta is about learning. Do not chase more features.
Build. Measure. Learn. Improve. Repeat.
