# AI Career Copilot — Post-Beta Roadmap (Parking Lot)

**Status:** Active parking lot — nothing in this file gets built during beta.
**Owner:** Gargey Patel

When a new idea fails any of the three questions (helps users apply faster? /
supportable with real data? / essential for beta?), it lands here instead of in
the codebase. Review after beta validation, prioritize by user feedback.

---

## Platform & Accounts

- **Full authentication** — magic-link email login first, then optional
  password/OAuth. (Beta decision: private dashboard links, no login wall.)
- Self-serve account & data deletion (beta: via founder email).
- Team accounts, recruiter portal / recruiter CRM.
- Premium plans, billing.

## Tracking & Intelligence

- **Interview tracking** — Gmail / Outlook / Google Calendar integrations,
  manual status updates. Until then the dashboard never displays Applications /
  Interviews / Offers.
- Offer tracking, salary insights / salary predictor.
- Career analytics dashboards.
- Application Intelligence Report (job summary, company overview, interview
  prep, cover letter, tips — per application).
- Preference & behavior learning in matching.

## AI Modules

- Cover Letter Generator (most-requested; first candidate after beta).
- Interview Question Generator / AI Interview Coach.
- LinkedIn Optimizer, Portfolio Optimizer.
- AI Chat Assistant / AI Career Agent.
- OCR for scanned resumes.

## Resume & Portfolio

- More templates: Creative, Executive, ATS Ultra, Academic.
- Live template preview with the user's own data during signup.
- Portfolio Builder; Behance / Dribbble / GitHub / Figma imports.
- Personal Website Generator.
- Project images/attachments.
- Draft autosave in the profile editor.

## Distribution & Surfaces

- Chrome extension (one-click apply from job boards).
- Mobile app.
- Job sources expansion: LinkedIn, Indeed, Wellfound, company career pages,
  government portals (marketing may only name sources actually live).

## Engineering Debt (scheduled, not forgotten)

- Next.js 15/16 major upgrade (remaining npm-audit advisories are only fixed
  there; 14.2.x is fully patched otherwise).
- Repository restructure (deferred until after first public beta by decision).
- Real background job queue if Render free-tier BackgroundTasks become a
  bottleneck.
- Paid-tier hosting review once cohort > ~100 active users (Render cold
  starts, Gemini/Adzuna quotas).

## UI / Cosmetic

- Dark mode, themes.
- Profile photo.
