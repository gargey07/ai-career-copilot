"""
Skill Maps — Per-category skill expansion & job search config
─────────────────────────────────────────────────────────────
When a user says "I know Figma" we know they also imply
prototyping, wireframing, dev handoff, etc.

This file defines:
  1. JOB_CATEGORIES  — all supported job categories
  2. SKILL_EXPANSION — core skill → implied skills per category
  3. expand_skills() — main function used by optimizer
"""
import re

# ── Category Definitions ──────────────────────────────────────────────────────

JOB_CATEGORIES = {
    "ui_ux_designer": {
        "label": "UI/UX Designer",
        "search_queries": ["UI UX Designer", "Product Designer", "UX Designer"],
        "target_roles": [
            "UI/UX Designer", "Product Designer", "Visual Designer",
            "Interaction Designer", "UX Researcher", "UX Writer",
            "Motion Designer", "Design Lead",
        ],
        "tools": [
            "Figma", "Adobe XD", "Sketch", "Illustrator", "Photoshop",
            "After Effects", "InDesign", "Principle", "Framer", "Webflow",
            "Maze", "Hotjar", "Miro", "FigJam", "Zeplin", "Notion",
            "UserTesting", "Optimal Workshop", "Lottie",
        ],
        "skills": [
            "User Research", "Usability Testing", "Wireframing", "Prototyping",
            "Design Systems", "Information Architecture", "User Flows",
            "Journey Mapping", "A/B Testing", "Heatmap Analysis",
            "Motion Design", "Accessibility", "Responsive Design",
            "Visual Hierarchy", "Typography", "Color Theory",
            "Interaction Design", "Design Thinking", "Stakeholder Presentations",
            "Design Critique", "Micro-interactions",
        ],
    },
    "frontend_developer": {
        "label": "Frontend Developer",
        "search_queries": ["Frontend Developer", "React Developer", "UI Developer"],
        "target_roles": [
            "Frontend Developer", "React Developer", "UI Developer",
            "JavaScript Developer", "Vue Developer", "Angular Developer",
        ],
        "tools": [
            "React", "Next.js", "Vue", "Angular", "TypeScript", "JavaScript",
            "HTML", "CSS", "Tailwind CSS", "SASS", "Redux", "Zustand",
            "GraphQL", "Webpack", "Vite", "Jest", "Cypress", "Storybook",
            "Git", "GitHub", "Figma", "VS Code", "Chrome DevTools",
        ],
        "skills": [
            "Responsive Design", "Accessibility (WCAG)", "Performance Optimization",
            "Cross-browser Compatibility", "Component Architecture",
            "State Management", "REST API Integration", "Code Review",
            "Unit Testing", "CI/CD", "SEO Basics", "Web Vitals",
            "Agile/Scrum", "Technical Documentation",
        ],
    },
    "backend_developer": {
        "label": "Backend Developer",
        "search_queries": ["Backend Developer", "Node.js Developer", "Python Developer"],
        "target_roles": [
            "Backend Developer", "Node.js Developer", "Python Developer",
            "Java Developer", "Go Developer", "API Developer",
        ],
        "tools": [
            "Python", "Node.js", "Java", "Go", "Ruby", "PHP",
            "FastAPI", "Django", "Express", "Spring Boot",
            "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
            "Docker", "Kubernetes", "AWS", "GCP", "Azure",
            "Git", "Postman", "Terraform", "Nginx",
        ],
        "skills": [
            "REST API Design", "GraphQL", "Microservices", "System Design",
            "Database Design", "Query Optimization", "Authentication & Auth",
            "Caching Strategies", "Message Queues", "CI/CD Pipelines",
            "Security Best Practices", "Code Review", "Agile/Scrum",
            "Technical Documentation", "Load Testing",
        ],
    },
    "fullstack_developer": {
        "label": "Fullstack Developer",
        "search_queries": ["Fullstack Developer", "Full Stack Developer", "MERN Developer"],
        "target_roles": [
            "Fullstack Developer", "Full Stack Developer",
            "MERN Stack Developer", "MEAN Stack Developer",
        ],
        "tools": [
            "React", "Next.js", "TypeScript", "Node.js", "Python",
            "PostgreSQL", "MongoDB", "Redis", "Docker", "AWS",
            "Git", "GitHub", "Figma", "Postman", "VS Code",
        ],
        "skills": [
            "REST API Design", "State Management", "Responsive Design",
            "Database Design", "Authentication & Auth", "System Design",
            "CI/CD Pipelines", "Code Review", "Agile/Scrum",
            "Performance Optimization", "Security Best Practices",
        ],
    },
    "product_manager": {
        "label": "Product Manager",
        "search_queries": ["Product Manager", "Product Owner", "Associate PM"],
        "target_roles": [
            "Product Manager", "Senior PM", "Associate PM",
            "Product Owner", "Technical PM",
        ],
        "tools": [
            "Jira", "Confluence", "Notion", "Figma", "Miro",
            "Mixpanel", "Amplitude", "Google Analytics", "Tableau",
            "Productboard", "Linear", "Asana", "Slack", "SQL",
        ],
        "skills": [
            "Product Roadmapping", "Agile", "Scrum", "OKRs",
            "User Research", "Customer Discovery", "A/B Testing",
            "PRD Writing", "Stakeholder Management", "Data Analysis",
            "Competitive Analysis", "Go-to-Market Strategy",
            "Prioritization Frameworks", "Sprint Planning", "Growth",
        ],
    },
    "data_scientist": {
        "label": "Data Scientist / ML",
        "search_queries": ["Data Scientist", "Machine Learning Engineer", "ML Engineer"],
        "target_roles": [
            "Data Scientist", "ML Engineer", "Machine Learning Engineer",
            "AI Engineer", "Data Analyst", "Research Scientist",
        ],
        "tools": [
            "Python", "R", "SQL", "Pandas", "NumPy", "Scikit-learn",
            "TensorFlow", "PyTorch", "Keras", "XGBoost", "LightGBM",
            "Jupyter", "Matplotlib", "Seaborn", "Tableau", "Power BI",
            "Spark", "Airflow", "MLflow", "Docker", "AWS", "GCP",
        ],
        "skills": [
            "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
            "Statistics", "A/B Testing", "Feature Engineering",
            "Model Evaluation", "Data Wrangling", "EDA",
            "Data Visualization", "Hypothesis Testing", "Time Series Analysis",
            "Model Deployment", "Research & Experimentation",
        ],
    },
    "devops_engineer": {
        "label": "DevOps / Cloud / SRE",
        "search_queries": ["DevOps Engineer", "Site Reliability Engineer", "Cloud Engineer"],
        "target_roles": [
            "DevOps Engineer", "Site Reliability Engineer", "Cloud Engineer",
            "Platform Engineer", "Infrastructure Engineer", "Cloud Architect",
        ],
        "tools": [
            "Docker", "Kubernetes", "Terraform", "Ansible", "Jenkins", "GitHub Actions",
            "GitLab CI", "AWS", "GCP", "Azure", "Prometheus", "Grafana", "Datadog",
            "Helm", "ArgoCD", "Nginx", "Linux", "Bash", "Python", "Go",
        ],
        "skills": [
            "CI/CD Pipelines", "Infrastructure as Code", "Container Orchestration",
            "Monitoring & Observability", "Incident Response", "Cloud Architecture",
            "Networking", "Security Hardening", "Auto-scaling", "Cost Optimization",
            "Site Reliability", "Load Balancing", "Disaster Recovery",
        ],
    },
    "data_engineer": {
        "label": "Data Engineer",
        "search_queries": ["Data Engineer", "Analytics Engineer", "ETL Developer"],
        "target_roles": [
            "Data Engineer", "Analytics Engineer", "ETL Developer",
            "Big Data Engineer", "Data Platform Engineer",
        ],
        "tools": [
            "Python", "SQL", "Spark", "Airflow", "dbt", "Kafka", "Snowflake",
            "BigQuery", "Redshift", "Databricks", "Hadoop", "Flink", "AWS",
            "GCP", "PostgreSQL", "Docker", "Terraform",
        ],
        "skills": [
            "Data Pipelines", "ETL / ELT", "Data Modeling", "Data Warehousing",
            "Stream Processing", "Batch Processing", "Data Quality", "Orchestration",
            "SQL Optimization", "Schema Design", "Data Governance",
        ],
    },
    "mobile_developer": {
        "label": "Mobile Developer",
        "search_queries": ["Mobile Developer", "iOS Developer", "Android Developer"],
        "target_roles": [
            "Mobile Developer", "iOS Developer", "Android Developer",
            "React Native Developer", "Flutter Developer",
        ],
        "tools": [
            "Swift", "SwiftUI", "Kotlin", "Java", "React Native", "Flutter", "Dart",
            "Xcode", "Android Studio", "Firebase", "Expo", "Fastlane", "Git",
        ],
        "skills": [
            "Mobile UI", "REST API Integration", "State Management", "Push Notifications",
            "App Store Deployment", "Offline Storage", "Performance Optimization",
            "Responsive Layouts", "Unit Testing", "Accessibility",
        ],
    },
    "qa_engineer": {
        "label": "QA / Test Engineer",
        "search_queries": ["QA Engineer", "Test Automation Engineer", "SDET"],
        "target_roles": [
            "QA Engineer", "Test Automation Engineer", "SDET",
            "Manual QA", "Quality Analyst", "Performance Test Engineer",
        ],
        "tools": [
            "Selenium", "Cypress", "Playwright", "Appium", "JUnit", "TestNG", "Jest",
            "Postman", "JMeter", "Jira", "TestRail", "Git", "Jenkins",
        ],
        "skills": [
            "Test Automation", "Manual Testing", "Test Case Design", "Regression Testing",
            "API Testing", "Performance Testing", "Bug Tracking", "CI Integration",
            "Exploratory Testing", "Test Planning",
        ],
    },
    "project_manager": {
        "label": "Project / Program Manager",
        "search_queries": ["Project Manager", "Program Manager", "Scrum Master"],
        "target_roles": [
            "Project Manager", "Program Manager", "Scrum Master",
            "Delivery Manager", "Technical Project Manager",
        ],
        "tools": [
            "Jira", "Asana", "Trello", "Monday.com", "Confluence", "Notion",
            "MS Project", "Smartsheet", "Slack", "Miro", "Excel",
        ],
        "skills": [
            "Agile", "Scrum", "Kanban", "Roadmapping", "Risk Management",
            "Stakeholder Management", "Resource Planning", "Budgeting",
            "Sprint Planning", "Reporting", "Cross-functional Leadership",
        ],
    },
    "digital_marketer": {
        "label": "Digital Marketing",
        "search_queries": ["Digital Marketer", "Growth Marketer", "SEO Specialist"],
        "target_roles": [
            "Digital Marketer", "Growth Marketer", "SEO Specialist",
            "Performance Marketer", "Content Marketer", "Social Media Manager",
        ],
        "tools": [
            "Google Analytics", "Google Ads", "Meta Ads", "SEMrush", "Ahrefs",
            "HubSpot", "Mailchimp", "Hootsuite", "Canva", "Google Tag Manager",
            "Looker Studio", "WordPress",
        ],
        "skills": [
            "SEO", "SEM", "Paid Media", "Email Marketing", "Content Strategy",
            "Conversion Optimization", "Social Media Marketing", "Marketing Analytics",
            "A/B Testing", "Copywriting", "Campaign Management", "Growth Hacking",
        ],
    },
    "sales": {
        "label": "Sales / Business Dev",
        "search_queries": ["Sales Executive", "Account Executive", "Business Development"],
        "target_roles": [
            "Sales Executive", "Account Executive", "Business Development Manager",
            "Sales Development Representative", "Account Manager", "Inside Sales",
        ],
        "tools": [
            "Salesforce", "HubSpot", "Outreach", "Salesloft", "LinkedIn Sales Navigator",
            "Pipedrive", "Zoho CRM", "Gong", "Apollo", "Excel",
        ],
        "skills": [
            "Lead Generation", "Prospecting", "Cold Outreach", "Negotiation",
            "Pipeline Management", "CRM Management", "Account Management",
            "Closing", "Relationship Building", "Sales Forecasting", "Upselling",
        ],
    },
    "content_writer": {
        "label": "Content / Copywriting",
        "search_queries": ["Content Writer", "Copywriter", "Technical Writer"],
        "target_roles": [
            "Content Writer", "Copywriter", "Technical Writer",
            "Content Strategist", "Editor", "UX Writer",
        ],
        "tools": [
            "Google Docs", "Notion", "WordPress", "Grammarly", "SurferSEO",
            "Ahrefs", "Canva", "Figma", "Hemingway", "Contentful",
        ],
        "skills": [
            "Copywriting", "Content Strategy", "SEO Writing", "Editing", "Storytelling",
            "Technical Documentation", "Research", "Brand Voice", "Proofreading",
            "Content Planning", "Long-form Writing",
        ],
    },
    "hr_recruiter": {
        "label": "HR / Recruiting",
        "search_queries": ["HR Manager", "Recruiter", "Talent Acquisition"],
        "target_roles": [
            "HR Manager", "Recruiter", "Talent Acquisition Specialist",
            "HR Business Partner", "People Operations", "HR Generalist",
        ],
        "tools": [
            "Workday", "Greenhouse", "Lever", "BambooHR", "LinkedIn Recruiter",
            "Naukri", "Indeed", "SAP SuccessFactors", "Excel", "Notion",
        ],
        "skills": [
            "Talent Acquisition", "Sourcing", "Interviewing", "Onboarding",
            "Employee Relations", "Performance Management", "HR Policy",
            "Compensation & Benefits", "Stakeholder Management", "HR Analytics",
        ],
    },
    "finance_analyst": {
        "label": "Finance / Accounting",
        "search_queries": ["Financial Analyst", "Accountant", "FP&A Analyst"],
        "target_roles": [
            "Financial Analyst", "Accountant", "FP&A Analyst",
            "Finance Manager", "Investment Analyst", "Auditor",
        ],
        "tools": [
            "Excel", "QuickBooks", "SAP", "Oracle", "Tally", "Power BI",
            "Tableau", "SQL", "NetSuite", "Bloomberg Terminal",
        ],
        "skills": [
            "Financial Modeling", "Forecasting", "Budgeting", "Variance Analysis",
            "Financial Reporting", "Valuation", "Accounting", "Auditing",
            "Data Analysis", "Cash Flow Management", "Compliance",
        ],
    },
    "graphic_designer": {
        "label": "Graphic / Brand Design",
        "search_queries": ["Graphic Designer", "Brand Designer", "Visual Designer"],
        "target_roles": [
            "Graphic Designer", "Brand Designer", "Visual Designer",
            "Illustrator", "Art Director", "Marketing Designer",
        ],
        "tools": [
            "Photoshop", "Illustrator", "InDesign", "Figma", "After Effects",
            "Canva", "Procreate", "CorelDRAW", "Blender", "Lightroom",
        ],
        "skills": [
            "Brand Identity", "Typography", "Layout Design", "Illustration",
            "Logo Design", "Color Theory", "Print Design", "Social Media Graphics",
            "Motion Graphics", "Visual Storytelling", "Packaging Design",
        ],
    },
}


# ── Skill Expansion Maps ──────────────────────────────────────────────────────
# When user mentions a skill, we know they also imply these related skills.
# Used to surface hidden skills for ATS matching.

SKILL_EXPANSION = {
    # ── Design Tools ──
    "figma": [
        "Prototyping", "Wireframing", "Component Design", "Auto-layout",
        "Design Tokens", "Dev Handoff", "Interactive Prototypes",
        "Design Systems", "Collaborative Design",
    ],
    "adobe xd": [
        "Prototyping", "Wireframing", "UI Design", "Responsive Design",
    ],
    "illustrator": [
        "Vector Graphics", "Icon Design", "Brand Identity", "Typography",
        "Print Design", "Logo Design",
    ],
    "photoshop": [
        "Photo Editing", "Image Manipulation", "Visual Design",
        "Digital Illustration", "Mockup Creation",
    ],
    "after effects": [
        "Motion Design", "Animation", "Micro-interactions",
        "Video Editing", "Motion Graphics",
    ],

    # ── UX Skills ──
    "user research": [
        "User Interviews", "Usability Testing", "Survey Design",
        "Contextual Inquiry", "Diary Studies", "Research Synthesis",
        "Affinity Mapping", "Persona Creation",
    ],
    "ux design": [
        "User Research", "Information Architecture", "User Flows",
        "Journey Mapping", "Wireframing", "Prototyping",
        "Usability Testing", "User-Centered Design",
    ],
    "ui design": [
        "Visual Hierarchy", "Typography", "Color Theory",
        "Component Design", "Responsive Design", "Accessibility",
        "Style Guides", "Design Systems",
    ],
    "design systems": [
        "Component Libraries", "Design Tokens", "Style Guides",
        "Pattern Libraries", "Atomic Design", "Documentation",
    ],
    "wireframing": [
        "Low-fidelity Prototypes", "Information Architecture",
        "User Flows", "Sketching", "Rapid Prototyping",
    ],

    # ── Frontend ──
    "react": [
        "React Hooks", "Component Architecture", "State Management",
        "JSX", "React Router", "Context API", "Custom Hooks",
    ],
    "next.js": [
        "SSR", "SSG", "ISR", "App Router", "API Routes",
        "Server Components", "Edge Functions",
    ],
    "typescript": [
        "Type Safety", "Interfaces", "Generics", "Type Guards",
        "Strict Mode", "TSConfig",
    ],
    "javascript": [
        "ES6+", "Async/Await", "Promises", "DOM Manipulation",
        "Event Handling", "Closures", "Prototypal Inheritance",
    ],
    "css": [
        "Flexbox", "CSS Grid", "Responsive Design", "CSS Animations",
        "BEM", "CSS Variables", "Media Queries",
    ],
    "tailwind css": [
        "Utility-first CSS", "Responsive Design", "Dark Mode",
        "Custom Configuration", "Component Styling",
    ],

    # ── Backend ──
    "python": [
        "Object-Oriented Programming", "Scripting", "Automation",
        "Data Processing", "REST APIs", "Async Programming",
    ],
    "node.js": [
        "Event-driven Architecture", "NPM", "Express",
        "Async Programming", "Streams", "REST APIs",
    ],
    "postgresql": [
        "SQL", "Database Design", "Indexing", "Query Optimization",
        "Transactions", "Stored Procedures",
    ],
    "docker": [
        "Containerization", "Docker Compose", "Image Building",
        "Container Orchestration", "Environment Management",
    ],
    "aws": [
        "Cloud Computing", "S3", "EC2", "Lambda", "RDS",
        "CloudFront", "IAM", "Serverless",
    ],

    # ── ML / Data ──
    "machine learning": [
        "Supervised Learning", "Unsupervised Learning", "Model Training",
        "Feature Engineering", "Model Evaluation", "Cross-validation",
        "Hyperparameter Tuning",
    ],
    "python (data)": [
        "Pandas", "NumPy", "Scikit-learn", "Jupyter Notebooks",
        "Data Wrangling", "EDA",
    ],
    "sql": [
        "Database Queries", "Joins", "Aggregations", "Window Functions",
        "Query Optimization", "Data Modeling",
    ],
}


# ── Helper Functions ──────────────────────────────────────────────────────────

def get_category(job_category: str) -> dict:
    """Get category config. Falls back to ui_ux_designer."""
    return JOB_CATEGORIES.get(job_category, JOB_CATEGORIES["ui_ux_designer"])


def get_search_queries(job_category: str) -> list[str]:
    """Get search queries for fetching jobs for this category."""
    return get_category(job_category)["search_queries"]


def all_categories() -> list[dict]:
    """[{value, label}, ...] for every job category — powers the tile grid + 'Other' search fallback."""
    return [{"value": key, "label": cat["label"]} for key, cat in JOB_CATEGORIES.items()]


def _flatten(field: str) -> list[str]:
    """Deduped, order-preserving flat list of a field across every job category."""
    seen: set[str] = set()
    out: list[str] = []
    for cat in JOB_CATEGORIES.values():
        for item in cat.get(field, []):
            if item.lower() not in seen:
                seen.add(item.lower())
                out.append(item)
    return out


# Computed once at import time — static data, cheap to flatten.
ALL_ROLES  = _flatten("target_roles")
ALL_TOOLS  = _flatten("tools")
ALL_SKILLS = _flatten("skills")

_SUGGESTION_SOURCES = {"roles": ALL_ROLES, "tools": ALL_TOOLS, "skills": ALL_SKILLS}


def _tokenize_role_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#.]+", text.lower()) if len(w) >= 2}


def _category_vocab(cat: dict) -> set[str]:
    """A category's own human-facing role vocabulary — its label plus every
    target_role phrase — as a token set. Deliberately NOT the snake_case
    dict key: 'product' and 'ai' never appear in any key (ui_ux_designer,
    product_manager, ...) but very much appear in real role labels
    ('Product Designer', 'AI Engineer'), which is exactly what let a
    Product Designer job pass a developer's category gate on 'product'
    alone (2026-07 production incident, Kevin's profile)."""
    return _tokenize_role_words(cat["label"] + " " + " ".join(cat["target_roles"]))


# A word counts as "generic" the moment it belongs to MORE THAN ONE
# category's real role vocabulary — computed mechanically from
# JOB_CATEGORIES itself, not a hand-maintained list. This is the single
# shared source of truth for "this word alone doesn't prove which
# profession a job belongs to": both core/matcher.py's match-time gate and
# jobs/fetchers.py's fetch-time title filter import this SAME set, so a
# future ambiguous word (e.g. 'writer', shared by ui_ux_designer's "UX
# Writer" and content_writer's "UX Writer"/"Content Writer") is caught in
# both places automatically the moment it exists in the data — no risk of
# one file getting a word-list update the other doesn't.
_CATEGORY_VOCABS = [_category_vocab(cat) for cat in JOB_CATEGORIES.values()]
GENERIC_ROLE_WORDS: set[str] = {
    word
    for vocab in _CATEGORY_VOCABS
    for word in vocab
    if sum(1 for v in _CATEGORY_VOCABS if word in v) > 1
}


def suggest(field: str, query: str, limit: int = 20) -> list[str]:
    """
    Type-ahead suggestions for roles/tools/skills across every job family,
    not just one category — backs the search-select fields in onboarding.
    Prefix matches rank above substring matches; no query returns the
    (already curated) full list up to `limit`.
    """
    source = _SUGGESTION_SOURCES.get(field)
    if source is None:
        raise ValueError(f"Unknown suggestion field: '{field}' (expected roles/tools/skills)")

    q = query.strip().lower()
    if not q:
        return source[:limit]

    prefix_matches = [item for item in source if item.lower().startswith(q)]
    substring_matches = [item for item in source if q in item.lower() and item not in prefix_matches]
    return (prefix_matches + substring_matches)[:limit]


def expand_skills(
    user_tools: list[str],
    user_skills: list[str],
    job_category: str,
) -> dict:
    """
    Expand user's tools + skills with implied related items.
    Returns separate expanded tools and skills lists.
    """
    # Expand tools
    expanded_tools = list(user_tools)
    seen_tools = {t.lower() for t in user_tools}
    for tool in user_tools:
        for implied in SKILL_EXPANSION.get(tool.lower(), []):
            if implied.lower() not in seen_tools:
                expanded_tools.append(implied)
                seen_tools.add(implied.lower())

    # Expand skills
    expanded_skills = list(user_skills)
    seen_skills = {s.lower() for s in user_skills}
    for skill in user_skills:
        for implied in SKILL_EXPANSION.get(skill.lower(), []):
            if implied.lower() not in seen_skills:
                expanded_skills.append(implied)
                seen_skills.add(implied.lower())

    return {
        "expanded_tools": expanded_tools,
        "expanded_skills": expanded_skills,
        "all_expanded": expanded_tools + [s for s in expanded_skills if s.lower() not in seen_tools],
    }


def match_skills_to_job(
    user_tools: list[str],
    user_skills: list[str],
    job_description: str,
    job_category: str,
) -> dict:
    """
    Compare expanded tools + skills against job description.
    Returns matched, missing, and expanded lists.
    """
    expanded = expand_skills(user_tools, user_skills, job_category)
    all_expanded = expanded["all_expanded"]
    jd_lower = job_description.lower()

    matched = [s for s in all_expanded if s.lower() in jd_lower]

    cat = get_category(job_category)
    all_cat_items = cat.get("tools", []) + cat.get("skills", [])
    missing = [s for s in all_cat_items if s.lower() in jd_lower and s.lower() not in {x.lower() for x in all_expanded}]

    score = round(len(matched) / max(len(all_expanded), 1) * 100)

    return {
        "matched_skills": matched,
        "missing_skills": missing[:5],
        "skill_match_score": score,
        "expanded_tools": expanded["expanded_tools"],
        "expanded_skills": expanded["expanded_skills"],
        "all_expanded": all_expanded,
    }
