# AI Career Copilot — AI Resume Intelligence Engine

**Version:** 1.1 Beta
**Status:** Active
**Owner:** Gargey Patel

---

## Vision

The AI Resume Engine is not a resume writer. It is an intelligent resume
optimization system. Its purpose is to understand the candidate, the job, and
the recruiter — and create the strongest possible application **without
inventing information**.

## Core Philosophy

Our AI does NOT create fake resumes. It creates better versions of the user's
own resume. Everything written must already exist somewhere in the user's
profile.

## AI Principles

The AI MUST: rewrite, reorganize, summarize, highlight, improve readability,
improve ATS compatibility, and explain every change.

The AI MUST NEVER invent: jobs, companies, skills, certificates, projects,
achievements, numbers, years, or promotions.

**Trust is more valuable than optimization.**

---

## Resume Generation Pipeline

User Resume → Resume Parser → Candidate Profile Builder → Job Analysis →
Keyword Extraction → Skill Matching → Gap Analysis → Resume Optimization →
Change Report → ATS Report → Resume PDF → Application Package

### Step 1 — Resume Parsing
Extract basic information, professional summary, experience, projects,
education, skills, certificates, portfolio, languages, achievements, contact
information. Everything becomes structured data.

### Step 2 — Candidate Profile Builder
The resume becomes an internal profile: experience, projects, skills, industry,
career level, tools, strengths, weaknesses. This profile is the source of truth
for every downstream AI module.

### Step 3 — Job Analysis
From the job description extract: title, industry, experience level, required
skills, preferred skills, technologies, responsibilities, education, location,
salary (optional), soft skills, keywords, culture, company info (future).

### Step 4 — Keyword Extraction
Classify keywords as high / medium / nice-to-have priority. These become
optimization targets.

### Step 5 — Resume Matching
Multiple scores instead of one: Overall, Skill, Experience, Project, Education,
Tool, Location, Portfolio match. Users should understand WHY they received the
score.

### Step 6 — Gap Analysis
Identify what's missing (e.g. Accessibility, Journey Mapping, Metrics) vs. what
is already strong (e.g. Figma, Wireframing, Research). This teaches users what
to improve.

### Step 7 — Resume Optimization
Improve: summary, experience, projects, skills, ordering, formatting, keyword
placement, readability, ATS compatibility. Never add information that doesn't
exist.

**Example** — Original: "Designed mobile applications." Optimized: "Designed
responsive mobile applications in Figma while collaborating with developers and
product managers to improve user experience." Only rewritten (using facts from
the profile). Nothing invented.

---

## Section Rules

- **Experience:** may rewrite/merge/reorder bullets, fix grammar, prioritize
  relevance. May never invent responsibilities, metrics, or achievements.
- **Projects:** one of the strongest matching signals — highlight technologies,
  responsibilities, impact, role, keywords. Never hidden.
- **Skills:** prioritize job-relevant skills and group them (Core / Tools /
  Soft). Only existing skills may be used.
- **Ordering:** sections may be reordered (e.g. Projects before Experience for
  a student) depending on the target job.
- **ATS:** improve keyword placement, hierarchy, formatting, readability,
  consistency, wording — without changing the truth.

---

## Transparency Artifacts

- **Change Report** — every generated resume includes a summary of what
  changed (e.g. "Experience: 3 bullets improved · Projects: reordered · Skills:
  prioritized · Formatting: improved").
- **Resume Diff** — side-by-side original vs. optimized lines.
- **AI Explain** — every change answerable: "Why did AI move project X above
  company Y?" → "The job emphasizes AI products and design systems; X
  demonstrates both." The AI is never a black box.
- **Resume Confidence** — e.g. High (92%): "Your resume already contains nearly
  all required experience." More useful than fake ATS scores.
- **ATS Report** — per-dimension (formatting, keywords, readability,
  experience, projects, skills, education) rather than a single opaque score.
- **Resume Versions** — original → v1 → v2 → …; users can restore any version.

## AI Safety Rules

May: rewrite, summarize, reorganize, highlight, prioritize, optimize.
May NEVER: invent, guess, assume, lie. If information is missing, leave it
unchanged.

## Failure Modes & Graceful Degradation (engineering contract)

The engine must never hard-fail a user flow:

- **Parsing fails / scanned image:** tell the user honestly and offer manual
  entry. Never guess at contents.
- **Job description too thin to analyze:** skip optimization for that job and
  say so ("Not enough job detail to tailor — original resume attached").
- **AI budget cap hit (see config daily limits):** fall back to the
  non-AI path (keyword matching, unmodified resume) and keep going. The
  pipeline continues; quality degrades before availability does.
- **PDF generation fails:** the match still appears on the dashboard without a
  PDF; retry next run.

Cost note: Change Report / Explain add AI calls per resume. They must reuse the
same generation call where possible (one prompt returning resume + change
summary together), and count against the daily Gemini budget.

## Application Intelligence Report (future USP)

Per application: job summary, company overview, resume match, resume changes,
missing skills, strengths, weaknesses, interview preparation, suggested cover
letter, application tips. Not just a PDF — an intelligence report.

## Future AI Modules

Cover Letter Generator, Interview Question Generator, LinkedIn Optimizer,
Portfolio Optimizer, Personal Website Generator, Career Coach, Salary Insights,
Recruiter Insights. Everything uses the same Candidate Profile.

## Success Metrics

Resume generated, resume downloaded, resume applied, user accepted changes,
resume match improvement, profile completion, returning users.

## Final Principle

AI should behave like an experienced recruiter and career coach. It improves
what already exists; it never invents what doesn't. The goal is not to create a
different candidate — it is to present the existing candidate in the strongest,
most truthful way possible.
