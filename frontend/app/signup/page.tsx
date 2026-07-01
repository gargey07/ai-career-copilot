"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

// ── Job Categories ────────────────────────────────────────────────────────────
const JOB_CATEGORIES = [
  { value: "ui_ux_designer",      label: "UI/UX Designer",       icon: "🎨" },
  { value: "frontend_developer",  label: "Frontend Developer",    icon: "💻" },
  { value: "backend_developer",   label: "Backend Developer",     icon: "⚙️" },
  { value: "fullstack_developer", label: "Fullstack Developer",   icon: "🚀" },
  { value: "product_manager",     label: "Product Manager",       icon: "📋" },
  { value: "data_scientist",      label: "Data Scientist / ML",   icon: "🤖" },
];

// ── Per-category roles, tools & skills ───────────────────────────────────────
const CATEGORY_CONFIG: Record<string, { roles: string[]; tools: string[]; skills: string[] }> = {
  ui_ux_designer: {
    roles: ["UI/UX Designer", "Product Designer", "Visual Designer", "Interaction Designer", "UX Researcher", "UX Writer", "Motion Designer", "Design Lead"],
    tools: ["Figma", "Adobe XD", "Sketch", "Illustrator", "Photoshop", "After Effects", "InDesign", "Principle", "Framer", "Webflow", "Maze", "Hotjar", "Miro", "FigJam", "Zeplin", "Notion", "UserTesting", "Lottie"],
    skills: ["User Research", "Usability Testing", "Wireframing", "Prototyping", "Design Systems", "Information Architecture", "User Flows", "Journey Mapping", "A/B Testing", "Heatmap Analysis", "Motion Design", "Accessibility", "Responsive Design", "Visual Hierarchy", "Typography", "Color Theory", "Interaction Design", "Design Thinking", "Micro-interactions"],
  },
  frontend_developer: {
    roles: ["Frontend Developer", "React Developer", "UI Developer", "JavaScript Developer", "Vue Developer", "Angular Developer"],
    tools: ["React", "Next.js", "Vue", "Angular", "TypeScript", "JavaScript", "HTML", "CSS", "Tailwind CSS", "SASS", "Redux", "Zustand", "GraphQL", "Webpack", "Vite", "Jest", "Cypress", "Storybook", "Git", "GitHub", "Figma", "VS Code"],
    skills: ["Responsive Design", "Accessibility (WCAG)", "Performance Optimization", "Cross-browser Compatibility", "Component Architecture", "State Management", "REST API Integration", "Code Review", "Unit Testing", "CI/CD", "SEO Basics", "Web Vitals", "Agile/Scrum"],
  },
  backend_developer: {
    roles: ["Backend Developer", "Node.js Developer", "Python Developer", "Java Developer", "Go Developer", "API Developer"],
    tools: ["Python", "Node.js", "Java", "Go", "FastAPI", "Django", "Express", "Spring Boot", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Git", "Postman", "Terraform"],
    skills: ["REST API Design", "GraphQL", "Microservices", "System Design", "Database Design", "Query Optimization", "Authentication & Auth", "Caching Strategies", "Message Queues", "CI/CD Pipelines", "Security Best Practices", "Code Review", "Agile/Scrum"],
  },
  fullstack_developer: {
    roles: ["Fullstack Developer", "Full Stack Developer", "MERN Stack Developer", "MEAN Stack Developer"],
    tools: ["React", "Next.js", "TypeScript", "Node.js", "Python", "PostgreSQL", "MongoDB", "Redis", "Docker", "AWS", "Git", "Figma", "Postman"],
    skills: ["REST API Design", "State Management", "Responsive Design", "Database Design", "Authentication & Auth", "System Design", "CI/CD Pipelines", "Code Review", "Performance Optimization", "Security Best Practices"],
  },
  product_manager: {
    roles: ["Product Manager", "Senior PM", "Associate PM", "Product Owner", "Technical PM"],
    tools: ["Jira", "Confluence", "Notion", "Figma", "Miro", "Mixpanel", "Amplitude", "Google Analytics", "Tableau", "Productboard", "Linear", "Asana", "Slack", "SQL"],
    skills: ["Product Roadmapping", "Agile", "Scrum", "OKRs", "User Research", "Customer Discovery", "A/B Testing", "PRD Writing", "Stakeholder Management", "Data Analysis", "Competitive Analysis", "Go-to-Market Strategy", "Prioritization Frameworks", "Sprint Planning"],
  },
  data_scientist: {
    roles: ["Data Scientist", "ML Engineer", "Machine Learning Engineer", "AI Engineer", "Data Analyst", "Research Scientist"],
    tools: ["Python", "R", "SQL", "Pandas", "NumPy", "Scikit-learn", "TensorFlow", "PyTorch", "XGBoost", "Jupyter", "Matplotlib", "Seaborn", "Tableau", "Power BI", "Spark", "Airflow", "MLflow", "Docker", "AWS"],
    skills: ["Machine Learning", "Deep Learning", "NLP", "Computer Vision", "Statistics", "A/B Testing", "Feature Engineering", "Model Evaluation", "Data Wrangling", "EDA", "Data Visualization", "Hypothesis Testing", "Time Series Analysis", "Model Deployment"],
  },
};

const LOCATIONS = ["Remote", "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Anywhere in India"];
const EXP_LEVELS = [
  { value: "fresher", label: "Fresher (0–1 yr)" },
  { value: "junior",  label: "Junior (1–3 yrs)" },
  { value: "mid",     label: "Mid (3–5 yrs)" },
  { value: "senior",  label: "Senior (5+ yrs)" },
];
const WORK_TYPES = ["Remote", "Onsite", "Hybrid"];

export default function SignupPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  const [form, setForm] = useState({
    name:                "",
    email:               "",
    phone:               "",
    job_category:        "",
    experience_level:    "junior",
    target_roles:        [] as string[],
    tools:               [] as string[],
    skills:              [] as string[],
    work_type:           [] as string[],
    preferred_locations: [] as string[],
    resume_text:         "",
  });

  const selectedConfig = form.job_category ? CATEGORY_CONFIG[form.job_category] : null;

  const toggle = (key: "target_roles" | "tools" | "skills" | "work_type" | "preferred_locations", val: string) => {
    setForm((f) => ({
      ...f,
      [key]: f[key].includes(val) ? f[key].filter((v) => v !== val) : [...f[key], val],
    }));
  };

  const selectCategory = (cat: string) => {
    setForm((f) => ({ ...f, job_category: cat, target_roles: [], tools: [], skills: [] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.job_category)              { setError("Please select your job category."); return; }
    if (!form.resume_text.trim())        { setError("Please paste your resume text."); return; }
    if (form.target_roles.length === 0)  { setError("Select at least one target role."); return; }
    if (form.tools.length === 0)         { setError("Select at least one tool you use."); return; }
    if (form.skills.length === 0)        { setError("Select at least one skill you have."); return; }

    setLoading(true);
    setError("");
    try {
      const { data, error: dbErr } = await supabase
        .from("users")
        .insert([{
          name:                form.name,
          email:               form.email,
          phone:               form.phone || null,
          job_category:        form.job_category,
          experience_level:    form.experience_level,
          target_roles:        form.target_roles,
          tools:               form.tools,
          skills:              form.skills,
          work_type:           form.work_type,
          preferred_locations: form.preferred_locations,
          resume_text:         form.resume_text.trim(),
          is_active:           true,
        }])
        .select("id")
        .single();

      if (dbErr) throw dbErr;
      router.push(`/success?name=${encodeURIComponent(form.name)}&id=${data.id}`);
    } catch (err: any) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const chipClass = (active: boolean) =>
    `cursor-pointer px-4 py-2 rounded-xl text-sm font-medium transition-all border ${
      active
        ? "bg-blue-600/30 border-blue-500 text-blue-300"
        : "border-white/10 text-gray-400 hover:border-white/20 hover:text-white"
    }`;

  return (
    <main className="min-h-screen flex flex-col" style={{ background: "#060614", color: "white" }}>
      {/* Background */}
      <div className="fixed inset-0 -z-10 pointer-events-none">
        <div className="absolute top-[-10%] left-[-5%]  w-[500px] h-[500px] rounded-full bg-blue-600/15   blur-[100px]" />
        <div className="absolute bottom-[-10%] right-[-5%] w-[400px] h-[400px] rounded-full bg-purple-600/15 blur-[100px]" />
      </div>

      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-5 max-w-4xl mx-auto w-full">
        <a href="/" className="flex items-center gap-2 group">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold text-white" style={{ background: "linear-gradient(135deg,#3b82f6,#8b5cf6)" }}>
            AI
          </div>
          <span className="font-semibold text-white group-hover:text-blue-300 transition-colors">Career Copilot</span>
        </a>
        <span className="text-sm text-gray-500">Free Beta — No credit card</span>
      </nav>

      {/* Form */}
      <div className="flex-1 flex items-start justify-center px-4 py-10">
        <div className="w-full max-w-2xl">
          <div className="text-center mb-10">
            <h1 className="text-4xl font-extrabold mb-3">
              Set up your{" "}
              <span style={{ background: "linear-gradient(135deg,#60a5fa,#a78bfa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                profile
              </span>
            </h1>
            <p className="text-gray-400">Takes 3 minutes. Your first digest arrives tomorrow at 7 AM.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-8">

            {/* ── Step 1: Job Category ── */}
            <div className="rounded-2xl p-8 space-y-6" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
              <div>
                <h2 className="font-semibold text-white text-lg">💼 What kind of jobs are you looking for?</h2>
                <p className="text-sm text-gray-500 mt-1">This helps us fetch the right jobs and expand your skills correctly.</p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {JOB_CATEGORIES.map((cat) => (
                  <button
                    key={cat.value}
                    type="button"
                    onClick={() => selectCategory(cat.value)}
                    className={`p-4 rounded-xl text-left transition-all border ${
                      form.job_category === cat.value
                        ? "bg-blue-600/20 border-blue-500 text-white"
                        : "border-white/10 text-gray-400 hover:border-white/20 hover:text-white"
                    }`}
                  >
                    <div className="text-2xl mb-2">{cat.icon}</div>
                    <div className="text-sm font-semibold">{cat.label}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* ── Step 2: About You ── */}
            <div className="rounded-2xl p-8 space-y-6" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
              <h2 className="font-semibold text-white text-lg">👤 About You</h2>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-2">Full Name *</label>
                  <input
                    required
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="Gargey Patel"
                    className="w-full px-4 py-3 rounded-xl text-white placeholder-gray-600 transition"
                    style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-2">Email *</label>
                  <input
                    required
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    placeholder="you@gmail.com"
                    className="w-full px-4 py-3 rounded-xl text-white placeholder-gray-600 transition"
                    style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">Phone (optional)</label>
                <input
                  type="tel"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  placeholder="+91 99254 77017"
                  className="w-full px-4 py-3 rounded-xl text-white placeholder-gray-600 transition"
                  style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-3">Experience Level *</label>
                <div className="flex flex-wrap gap-3">
                  {EXP_LEVELS.map((l) => (
                    <button key={l.value} type="button" onClick={() => setForm({ ...form, experience_level: l.value })} className={chipClass(form.experience_level === l.value)}>
                      {l.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* ── Step 3: Job Preferences (shows after category selected) ── */}
            {selectedConfig && (
              <div className="rounded-2xl p-8 space-y-6" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
                <h2 className="font-semibold text-white text-lg">🎯 Job Preferences</h2>

                <div>
                  <label className="block text-sm text-gray-400 mb-3">Target Roles * <span className="text-gray-600">(pick all that apply)</span></label>
                  <div className="flex flex-wrap gap-3">
                    {selectedConfig.roles.map((r) => (
                      <button key={r} type="button" onClick={() => toggle("target_roles", r)} className={chipClass(form.target_roles.includes(r))}>
                        {r}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Work Type</label>
                  <div className="flex flex-wrap gap-3">
                    {WORK_TYPES.map((w) => (
                      <button key={w} type="button" onClick={() => toggle("work_type", w)} className={chipClass(form.work_type.includes(w))}>
                        {w}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-3">Preferred Locations</label>
                  <div className="flex flex-wrap gap-3">
                    {LOCATIONS.map((loc) => (
                      <button key={loc} type="button" onClick={() => toggle("preferred_locations", loc)} className={chipClass(form.preferred_locations.includes(loc))}>
                        {loc}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ── Step 4a: Tools (shows after category selected) ── */}
            {selectedConfig && (
              <div className="rounded-2xl p-8 space-y-4" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
                <div>
                  <h2 className="font-semibold text-white text-lg">🛠️ Your Tools</h2>
                  <p className="text-sm text-gray-500 mt-1">
                    Select every tool / software you actually use. Select as many as you want.
                  </p>
                </div>

                {form.tools.length > 0 && (
                  <div className="text-sm font-medium" style={{ color: "#60a5fa" }}>
                    ✓ {form.tools.length} tools selected
                  </div>
                )}

                <div className="flex flex-wrap gap-3">
                  {selectedConfig.tools.map((tool) => (
                    <button key={tool} type="button" onClick={() => toggle("tools", tool)} className={chipClass(form.tools.includes(tool))}>
                      {tool}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-600">
                  💡 Our AI expands these automatically — e.g. "Figma" → Prototyping, Dev Handoff, Component Design.
                </p>
              </div>
            )}

            {/* ── Step 4b: Skills (shows after category selected) ── */}
            {selectedConfig && (
              <div className="rounded-2xl p-8 space-y-4" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
                <div>
                  <h2 className="font-semibold text-white text-lg">⚡ Your Skills</h2>
                  <p className="text-sm text-gray-500 mt-1">
                    Select competencies and abilities you have. Select as many as apply — more is better.
                  </p>
                </div>

                {form.skills.length > 0 && (
                  <div className="text-sm font-medium" style={{ color: "#a78bfa" }}>
                    ✓ {form.skills.length} skills selected
                  </div>
                )}

                <div className="flex flex-wrap gap-3">
                  {selectedConfig.skills.map((skill) => (
                    <button key={skill} type="button" onClick={() => toggle("skills", skill)} className={chipClass(form.skills.includes(skill))}>
                      {skill}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-600">
                  💡 These get reordered per job — most relevant skills always appear first on your resume.
                </p>
              </div>
            )}

            {/* ── Step 5: Resume ── */}
            <div className="rounded-2xl p-8 space-y-4" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
              <div>
                <h2 className="font-semibold text-white text-lg">📄 Your Resume</h2>
                <p className="text-sm text-gray-500 mt-1">
                  Paste your full resume as plain text. AI will tailor it for each job.
                </p>
              </div>
              <textarea
                required
                rows={12}
                value={form.resume_text}
                onChange={(e) => setForm({ ...form, resume_text: e.target.value })}
                placeholder={`YOUR NAME\nUI/UX Designer\n\nEMAIL: you@gmail.com  |  PHONE: +91 XXXXX XXXXX\n\nSUMMARY\nPassionate designer with X years of experience...\n\nEXPERIENCE\nUI/UX Designer — Company Name  (Jan 2024 – Present)\n• Designed...\n\nSKILLS\nFigma, Adobe XD, Illustrator...\n\nEDUCATION\nBachelor of...\n`}
                className="w-full px-4 py-3 rounded-xl text-white placeholder-gray-700 text-sm font-mono leading-relaxed transition resize-none"
                style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
              />
              <p className="text-xs text-gray-600">
                💡 Copy-paste from your existing resume. Plain text works best — no formatting needed.
              </p>
            </div>

            {/* Error */}
            {error && (
              <div className="rounded-xl px-4 py-3 text-red-400 text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)" }}>
                ⚠️ {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-4 rounded-xl font-bold text-white text-lg transition-all disabled:opacity-50"
              style={{ background: "linear-gradient(135deg,#3b82f6,#8b5cf6)" }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-3">
                  <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"/>
                  </svg>
                  Saving your profile...
                </span>
              ) : "Join Free Beta — Get My First Digest →"}
            </button>

            <p className="text-center text-sm text-gray-600">
              Free during beta · No credit card · Unsubscribe anytime
            </p>
          </form>
        </div>
      </div>
    </main>
  );
}
