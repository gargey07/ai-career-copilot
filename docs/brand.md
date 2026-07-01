# Brand

## Name
**AI Career Copilot** — the public product/brand name.

Single source of truth in code: `frontend/lib/brand.ts` (`BRAND_NAME`). Never hardcode the
name in components; import it. This makes a future rename a one-line change.

Tagline: *"Wake up to tailored jobs every morning."*

## Logo
Origami-style bird mark in the brand orange/teal palette. Pair the mark with the wordmark
in nav; the mark alone is fine as a favicon/avatar.

## Voice
Direct, encouraging, concrete. Short sentences. Speak to one person ("you"). No hype, no
jargon, no emojis in UI copy.

## Post-beta note (deferred)
The internal project/repo name should eventually be decoupled from the marketing name
(e.g. internal `career-platform`), with a folder restructure
(frontend/backend/shared/workers/scheduler/docs). Deliberately deferred until after the
first public beta to avoid destabilizing the live Render/Vercel deploys. Do not do this as
part of a UI change.
