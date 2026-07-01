so # Product Requirements Document (PRD)
# AI Career Copilot — v2.0

**Author:** Gargey Patel
**Contact:** gargeypatel123@gmail.com
**Status:** Active Development
**Last Updated:** 2026-06-29

---

## 1. Problem Statement

Job searching is an extremely time-consuming, repetitive, and demoralizing process. 

A typical job seeker spends:
- **2–3 hours/day** searching for relevant jobs across multiple platforms
- **30–60 minutes/job** tailoring their resume and writing a cover letter
- **Another 30 minutes** finding the right contact email / application link

Most people apply to jobs with a **generic resume**, resulting in a very low response rate.

---

## 2. Solution

**AI Career Copilot** eliminates all manual effort by:

1. **Collecting** 500+ fresh jobs daily from multiple platforms
2. **Ranking** the top matches against each user's profile (locally, without AI)
3. **Generating** ATS-optimized resumes and personalized cover letters **only for top matches** (using AI)
4. **Creating** a beautiful, professional PDF resume for each opportunity
5. **Delivering** a personalized morning digest email with everything ready to apply

> Users wake up, open email, review 3 tailored opportunities, and apply in under 10 minutes.

---

## 3. Target Users

### Beta (0–50 users)
- Students & fresh graduates actively job hunting
- Mid-level professionals switching roles or companies
- UI/UX Designers, Developers, Product Managers, Marketers

### Growth (50–1000 users)
- Any professional looking for job search automation
- Career-switchers who need strong resume customization

### Scale (1000+ users)
- General job seekers across all domains
- Companies (B2B) wanting to run this for bulk hiring

---

## 4. User Journey

```
1. User visits landing page
2. Signs up with Google or Email
3. Fills out their profile:
   - Target role(s)
   - Experience level
   - Location / Remote preference
   - Preferred salary range
   - Uploads or pastes resume
4. Next morning at 7 AM → receives email digest with:
   - Top 3 matched jobs
   - Tailored resume PDF for each job
   - Personalized cover letter for each job
   - Company email / direct apply link
5. User clicks apply → done in minutes
```

---

## 5. Core Features

### 5.1 Job Discovery
- Aggregate 500+ jobs daily from: LinkedIn, Indeed, Wellfound, RemoteOK, Adzuna, JSearch
- Normalize all jobs into a single schema
- Deduplicate across sources
- Store centrally for all users to share

### 5.2 Intelligent Matching
- Use vector embeddings to match jobs to user profiles
- Score jobs on: role similarity, experience level, location, salary, remote preference
- Select Top 10 matches per user for ranking
- Generate AI content for Top 3 only (cost optimization)

### 5.3 AI Resume Engine
- Rewrite resume summary for the target role
- Inject ATS keywords from the job description
- Reorder skills to highlight the most relevant ones
- Never fabricate experience (truthfulness validation)

### 5.4 Cover Letter Engine
- Generate personalized cover letters per job
- Reference specific company details
- Maintain user's voice and tone
- Keep it concise (250–300 words)

### 5.5 PDF Generation
- Render professional resume PDFs from HTML/Tailwind templates using Playwright
- Multiple resume template options (minimal, modern, bold)
- Store PDF in Cloudflare R2 / S3-compatible storage
- Generate a shareable link per PDF

### 5.6 Morning Digest Email
- Delivered at 7 AM (user's timezone)
- Beautiful, mobile-responsive HTML email
- Shows: match score, company, role, salary, location, apply options
- Includes PDF attachment or Drive link

### 5.7 Dashboard (Web)
- Today's job matches
- Resume library (all generated versions)
- Cover letter library
- Application status tracker (applied, interviewing, offer, rejected)

---

## 6. Non-Features (Out of Scope for v1.0)

- Auto-submitting applications (we never apply without the user)
- LinkedIn profile scraping or automation
- Browser extension
- Mobile app

---

## 7. Business Model

### Free Tier
- 3 resume optimizations/week
- Basic matching (top 5 jobs/day)
- Daily digest email

### Pro Tier (₹499/month or $9/month)
- Unlimited resume optimizations
- Top 10 jobs/day
- Priority AI processing
- Cover letters included
- Advanced analytics
- Interview preparation tips

### Enterprise (custom pricing)
- White-label solution
- Custom job sources
- Bulk user management

---

## 8. Success Metrics

| Metric | Target (Beta) | Target (3 months) |
|--------|--------------|-------------------|
| Daily Active Users | 5 | 50 |
| Avg. Resumes Generated/Day | 15 | 150 |
| Email Open Rate | > 50% | > 40% |
| User Activation (applied at least 1 job) | > 70% | > 60% |
| AI Cost per User/Day | < ₹2 | < ₹1 |

---

## 9. Constraints

- AI budget: < ₹5/user/day during beta
- PDF generation must be < 10 seconds per resume
- Email delivery must complete before 7:15 AM
- System must handle 1000 users with ≤ 2 VPS nodes
