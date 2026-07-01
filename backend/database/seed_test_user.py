"""
Seed Test Data — Insert a test user + fake jobs into Supabase
──────────────────────────────────────────────────────────────
Run this ONCE to populate the database so you can test the pipeline.

Usage:
    PYTHONPATH=. python3 database/seed_test_user.py
    PYTHONPATH=. python3 database/seed_test_user.py --clear   # wipe and re-seed
"""
import sys
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from database.supabase_client import get_supabase  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── Test User ─────────────────────────────────────────────────────────────────
TEST_USER = {
    "email": "gargey.test@gmail.com",
    "name": "Gargey Patel",
    "target_roles": ["UI/UX Designer", "Product Designer", "UX Researcher"],
    "experience_level": "mid",
    "preferred_locations": ["Mumbai", "Bangalore", "Remote"],
    "remote_preference": "any",
    "salary_min": 800000,
    "salary_max": 2000000,
    "tier": "free",
    "is_active": True,
    "timezone": "Asia/Kolkata",
    "resume_text": (
        "GARGEY PATEL\n"
        "UI/UX Designer | gargeypatel123@gmail.com | Mumbai, India\n\n"
        "SUMMARY\n"
        "Passionate UI/UX Designer with 3+ years of experience crafting intuitive digital experiences "
        "for web and mobile applications. Expert in user research, wireframing, and high-fidelity "
        "prototyping using Figma. Proven track record of improving user engagement by 40%+ through "
        "data-driven design decisions.\n\n"
        "PROFESSIONAL EXPERIENCE\n\n"
        "UI/UX Designer — TechStartup Pvt Ltd, Mumbai  (2022 – Present)\n"
        "• Led end-to-end design of the company's flagship SaaS dashboard serving 10,000+ users\n"
        "• Conducted 50+ user interviews and usability studies to inform design decisions\n"
        "• Reduced user onboarding drop-off by 35% through redesigned onboarding flow\n"
        "• Built and maintained a comprehensive design system with 200+ reusable components\n\n"
        "Junior UI Designer — Digital Agency XYZ, Pune  (2021 – 2022)\n"
        "• Designed mobile-first landing pages and e-commerce flows for 15+ client projects\n"
        "• Created brand identities and style guides for 5 startups\n\n"
        "SKILLS\n"
        "Design: Figma, Adobe XD, Sketch, Illustrator, Photoshop\n"
        "Research: User interviews, A/B testing, heatmap analysis, usability testing\n"
        "Prototyping: Interactive prototypes, micro-animations, design systems\n"
        "Frontend: Basic HTML/CSS, React component understanding\n"
        "Tools: Notion, Jira, Miro, Zeplin, Hotjar, Mixpanel\n\n"
        "EDUCATION\n"
        "B.Des in Communication Design — National Institute of Design, Ahmedabad  (2017–2021)"
    ),
}

# ── Fake Jobs (for testing without API keys) ──────────────────────────────────
_now = datetime.now(timezone.utc)

FAKE_JOBS = [
    {
        "source": "test_seed",
        "external_id": "test_job_001",
        "source_url": "https://example.com/jobs/ux-designer-google",
        "title": "Senior UX Designer",
        "company": "Google India",
        "location": "Bangalore, India",
        "description": (
            "We are looking for a Senior UX Designer to join our Workspace team.\n\n"
            "Requirements:\n"
            "- 4+ years of UX design experience\n"
            "- Expert in Figma and prototyping tools\n"
            "- Strong portfolio showing complex product design\n"
            "- Experience with user research and usability testing\n"
            "- Experience with design systems at scale\n\n"
            "Responsibilities:\n"
            "- Lead design for Google Workspace products used by millions\n"
            "- Conduct user research and synthesize insights\n"
            "- Create wireframes, prototypes, and high-fidelity mockups\n"
            "- Partner with engineers and PMs to ship high-quality products\n\n"
            "Salary: Rs 30-50 LPA + RSUs + benefits"
        ),
        "salary_min": 3000000,
        "salary_max": 5000000,
        "currency": "INR",
        "employment_type": "full-time",
        "seniority_level": "senior",
        "is_remote": False,
        "posted_at": (_now - timedelta(days=1)).isoformat(),
        "collected_at": _now.isoformat(),
    },
    {
        "source": "test_seed",
        "external_id": "test_job_002",
        "source_url": "https://example.com/jobs/product-designer-swiggy",
        "title": "Product Designer",
        "company": "Swiggy",
        "location": "Bangalore, India",
        "description": (
            "Swiggy is hiring a Product Designer for our Consumer Experience team.\n\n"
            "What you'll do:\n"
            "- Own design for key consumer journeys (discovery, ordering, tracking)\n"
            "- Run rapid design sprints and validate ideas with real users\n"
            "- Create pixel-perfect UI for iOS and Android apps\n"
            "- Build reusable components for our design system\n\n"
            "Requirements:\n"
            "- 3-5 years of product design experience\n"
            "- Strong visual design skills and attention to detail\n"
            "- Mobile-first design experience (iOS/Android)\n"
            "- Familiarity with motion design and micro-interactions\n\n"
            "Salary: Rs 25-40 LPA. Hybrid 3 days/week."
        ),
        "salary_min": 2500000,
        "salary_max": 4000000,
        "currency": "INR",
        "employment_type": "full-time",
        "seniority_level": "mid",
        "is_remote": False,
        "posted_at": (_now - timedelta(days=2)).isoformat(),
        "collected_at": _now.isoformat(),
    },
    {
        "source": "test_seed",
        "external_id": "test_job_003",
        "source_url": "https://example.com/jobs/ux-designer-remote-figr",
        "title": "UX Designer (Remote)",
        "company": "Figr",
        "location": "Remote — India",
        "description": (
            "Figr is a fast-growing design tools startup looking for a UX Designer to join remotely.\n\n"
            "Your role:\n"
            "- Design the core product experience for our web app\n"
            "- Conduct weekly user interviews with our designer customers\n"
            "- Translate insights into intuitive, delightful interfaces\n"
            "- Help define our design language and component library\n\n"
            "What we're looking for:\n"
            "- 2-4 years of UX/Product design experience\n"
            "- Experience designing SaaS or design tools (bonus!)\n"
            "- Strong portfolio with case studies\n"
            "- Comfortable working fully remote, async-first\n\n"
            "Salary: Rs 18-28 LPA + early-stage equity"
        ),
        "salary_min": 1800000,
        "salary_max": 2800000,
        "currency": "INR",
        "employment_type": "full-time",
        "seniority_level": "mid",
        "is_remote": True,
        "posted_at": (_now - timedelta(days=1)).isoformat(),
        "collected_at": _now.isoformat(),
    },
    {
        "source": "test_seed",
        "external_id": "test_job_004",
        "source_url": "https://example.com/jobs/ux-researcher-flipkart",
        "title": "UX Researcher",
        "company": "Flipkart",
        "location": "Bangalore, India",
        "description": (
            "Flipkart is looking for a UX Researcher to join our Design Research team.\n\n"
            "Responsibilities:\n"
            "- Plan and execute qualitative and quantitative research studies\n"
            "- Conduct usability tests, interviews, surveys, and diary studies\n"
            "- Synthesize research findings into actionable design insights\n"
            "- Present insights to leadership and cross-functional stakeholders\n\n"
            "Requirements:\n"
            "- 3+ years of UX research experience\n"
            "- Expertise in both qual and quant research methods\n"
            "- Experience with tools: UserTesting, Maze, Optimal Workshop\n"
            "- Strong analytical thinking and storytelling ability\n\n"
            "Compensation: Rs 22-35 LPA + ESOPs"
        ),
        "salary_min": 2200000,
        "salary_max": 3500000,
        "currency": "INR",
        "employment_type": "full-time",
        "seniority_level": "mid",
        "is_remote": False,
        "posted_at": (_now - timedelta(days=3)).isoformat(),
        "collected_at": _now.isoformat(),
    },
    {
        "source": "test_seed",
        "external_id": "test_job_005",
        "source_url": "https://example.com/jobs/ui-designer-razorpay",
        "title": "UI Designer",
        "company": "Razorpay",
        "location": "Bangalore / Remote",
        "description": (
            "Razorpay is hiring a UI Designer to help build the future of fintech in India.\n\n"
            "Key Responsibilities:\n"
            "- Create visually stunning UI for Razorpay's product suite\n"
            "- Develop and maintain our design system (Blade)\n"
            "- Collaborate with UX designers to bring wireframes to life\n"
            "- Ensure pixel-perfect implementation with engineering\n\n"
            "Required Skills:\n"
            "- 2-4 years of UI design experience\n"
            "- Expert-level Figma proficiency\n"
            "- Strong understanding of typography, color, and layout\n"
            "- Experience designing for web and mobile\n\n"
            "Salary: Rs 20-30 LPA"
        ),
        "salary_min": 2000000,
        "salary_max": 3000000,
        "currency": "INR",
        "employment_type": "full-time",
        "seniority_level": "mid",
        "is_remote": True,
        "posted_at": (_now - timedelta(days=2)).isoformat(),
        "collected_at": _now.isoformat(),
    },
]


# ── Seed Functions ────────────────────────────────────────────────────────────
def clear_test_data(supabase):
    """Remove all seed data — useful for re-running."""
    logger.info("Clearing existing test data...")
    try:
        supabase.table("user_jobs").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        supabase.table("users").delete().eq("email", TEST_USER["email"]).execute()
        supabase.table("jobs").delete().eq("source", "test_seed").execute()
        logger.info("   Cleared OK")
    except Exception as e:
        logger.warning(f"   Clear failed (may be fine on first run): {e}")


def seed_user(supabase) -> str:
    """Insert test user. Returns the user's UUID."""
    logger.info(f"Seeding test user: {TEST_USER['email']}")
    resp = (
        supabase.table("users")
        .upsert(TEST_USER, on_conflict="email", ignore_duplicates=False)
        .execute()
    )
    user_id = resp.data[0]["id"]
    logger.info(f"   User ID: {user_id}")
    return user_id


def seed_jobs(supabase) -> list:
    """Insert fake test jobs. Returns list of job UUIDs."""
    logger.info(f"Seeding {len(FAKE_JOBS)} test jobs...")
    resp = (
        supabase.table("jobs")
        .upsert(FAKE_JOBS, on_conflict="source_url", ignore_duplicates=False)
        .execute()
    )
    job_ids = [j["id"] for j in resp.data]
    logger.info(f"   {len(job_ids)} jobs seeded")
    return job_ids


def print_summary(user_id: str, job_ids: list):
    print("\n" + "=" * 60)
    print("SEED COMPLETE")
    print("=" * 60)
    print(f"\nTest User ID:\n  {user_id}")
    print(f"\nJobs seeded: {len(job_ids)}")
    print("\nNOTE: Jobs have no embeddings yet.")
    print("  - With GEMINI_API_KEY: vector matching works")
    print("  - Without it: falls back to recency sort (fine for testing)")
    print("\nNext steps:")
    print("  1. Add GEMINI_API_KEY to .env  (optional but recommended)")
    print("  2. Run the pipeline in test mode:")
    print("     PYTHONPATH=. python3 pipeline.py --test")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    supabase = get_supabase()

    if "--clear" in sys.argv:
        clear_test_data(supabase)

    user_id = seed_user(supabase)
    job_ids = seed_jobs(supabase)
    print_summary(user_id, job_ids)
