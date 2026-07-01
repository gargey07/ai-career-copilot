"use client";

import { useState } from "react";
import { API_URL } from "@/lib/api";
import type { Profile } from "@/lib/profile";
import { emptyEducation } from "@/lib/profile";
import ExperienceSection from "@/components/ExperienceSection";
import SearchSelect from "@/components/SearchSelect";

interface ReviewStepProps {
  initialProfile: Profile;
  resumeFilePath: string | null;
  onConfirmed: (id: string, name: string) => void;
}

const JOB_CATEGORIES = [
  { value: "ui_ux_designer",      label: "UI/UX Designer",       icon: "🎨" },
  { value: "frontend_developer",  label: "Frontend Developer",    icon: "💻" },
  { value: "backend_developer",   label: "Backend Developer",     icon: "⚙️" },
  { value: "fullstack_developer", label: "Fullstack Developer",   icon: "🚀" },
  { value: "product_manager",     label: "Product Manager",       icon: "📋" },
  { value: "data_scientist",      label: "Data Scientist / ML",   icon: "🤖" },
];

const LOCATIONS = ["Remote", "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Anywhere in India"];
const EXP_LEVELS = [
  { value: "fresher", label: "Fresher (0–1 yr)" },
  { value: "junior",  label: "Junior (1–3 yrs)" },
  { value: "mid",     label: "Mid (3–5 yrs)" },
  { value: "senior",  label: "Senior (5+ yrs)" },
];
const WORK_TYPES = ["Remote", "Onsite", "Hybrid"];

const cardStyle = { background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" };
const fieldStyle = { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" };
const fieldClass = "w-full px-4 py-3 rounded-xl text-white placeholder-gray-600 transition";

const chipClass = (active: boolean) =>
  `cursor-pointer px-4 py-2 rounded-xl text-sm font-medium transition-all border ${
    active
      ? "bg-blue-600/30 border-blue-500 text-blue-300"
      : "border-white/10 text-gray-400 hover:border-white/20 hover:text-white"
  }`;

export default function ReviewStep({ initialProfile, resumeFilePath, onConfirmed }: ReviewStepProps) {
  const [profile, setProfile] = useState<Profile>(initialProfile);
  const [otherCategory, setOtherCategory] = useState(
    initialProfile.job_category && !JOB_CATEGORIES.some((c) => c.value === initialProfile.job_category)
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const flag = (field: string) => profile.confidence_flags?.[field];

  const update = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setProfile((p) => ({ ...p, [key]: value }));

  const updateBasic = (key: keyof Profile["basic_info"], value: string) =>
    setProfile((p) => ({ ...p, basic_info: { ...p.basic_info, [key]: value } }));

  const updateLinks = (key: keyof Profile["links"], value: string) =>
    setProfile((p) => ({ ...p, links: { ...p.links, [key]: value } }));

  const toggleWorkType = (val: string) =>
    setProfile((p) => ({
      ...p,
      work_type: p.work_type.includes(val) ? p.work_type.filter((v) => v !== val) : [...p.work_type, val],
    }));

  const canSubmit = profile.basic_info.full_name.trim() && profile.basic_info.email.trim() && !loading;

  const handleConfirm = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/resumes/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...profile, resume_file_path: resumeFilePath }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Something went wrong saving your profile.");
      }
      const data = await res.json();
      onConfirmed(data.id, profile.basic_info.full_name);
    } catch (e: any) {
      setError(e.message || "Something went wrong. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="text-center">
        <p className="text-gray-400">
          Here&apos;s what we found in your resume. Double check everything looks right, then confirm.
        </p>
      </div>

      {/* ── Basic Info ── */}
      <div className="rounded-2xl p-8 space-y-4" style={cardStyle}>
        <h2 className="font-semibold text-white text-lg">👤 Basic Info</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Full Name *</label>
            <input
              required
              type="text"
              value={profile.basic_info.full_name}
              onChange={(e) => updateBasic("full_name", e.target.value)}
              placeholder="Gargey Patel"
              className={fieldClass}
              style={fieldStyle}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Email *</label>
            <input
              required
              type="email"
              value={profile.basic_info.email}
              onChange={(e) => updateBasic("email", e.target.value)}
              placeholder="you@gmail.com"
              className={fieldClass}
              style={fieldStyle}
            />
          </div>
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Phone</label>
            <input
              type="tel"
              value={profile.basic_info.phone}
              onChange={(e) => updateBasic("phone", e.target.value)}
              placeholder="+91 99254 77017"
              className={fieldClass}
              style={fieldStyle}
            />
            {flag("phone") && <p className="text-xs mt-1.5" style={{ color: "#fbbf24" }}>We couldn&apos;t find a phone number — add one?</p>}
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Location</label>
            <input
              type="text"
              value={profile.basic_info.location}
              onChange={(e) => updateBasic("location", e.target.value)}
              placeholder="Mumbai, India"
              className={fieldClass}
              style={fieldStyle}
            />
          </div>
        </div>
      </div>

      {/* ── Summary ── */}
      <div className="rounded-2xl p-8 space-y-3" style={cardStyle}>
        <h2 className="font-semibold text-white text-lg">✍️ Summary</h2>
        <textarea
          value={profile.summary}
          onChange={(e) => update("summary", e.target.value)}
          rows={3}
          placeholder="A short professional summary…"
          className={`${fieldClass} resize-none`}
          style={fieldStyle}
        />
        {flag("summary") && <p className="text-xs" style={{ color: "#fbbf24" }}>We&apos;re not fully confident in this summary — worth a quick edit.</p>}
      </div>

      {/* ── Experience ── */}
      <div className="rounded-2xl p-8 space-y-4" style={cardStyle}>
        <h2 className="font-semibold text-white text-lg">💼 Work Experience</h2>
        <ExperienceSection entries={profile.work_experience} onChange={(v) => update("work_experience", v)} />
      </div>

      {/* ── Education ── */}
      <div className="rounded-2xl p-8 space-y-4" style={cardStyle}>
        <h2 className="font-semibold text-white text-lg">🎓 Education</h2>
        <div className="space-y-3">
          {profile.education.map((edu, i) => (
            <div key={i} className="rounded-xl p-5 space-y-3" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}>
              <div className="flex justify-between items-start gap-3">
                <div className="grid sm:grid-cols-2 gap-3 flex-1">
                  <input type="text" value={edu.school} onChange={(e) => update("education", profile.education.map((x, j) => j === i ? { ...x, school: e.target.value } : x))} placeholder="School" className={fieldClass} style={fieldStyle} />
                  <input type="text" value={edu.degree} onChange={(e) => update("education", profile.education.map((x, j) => j === i ? { ...x, degree: e.target.value } : x))} placeholder="Degree" className={fieldClass} style={fieldStyle} />
                </div>
                <button type="button" onClick={() => update("education", profile.education.filter((_, j) => j !== i))} className="text-gray-500 hover:text-red-400 transition-colors text-sm px-2 py-2">
                  Remove
                </button>
              </div>
              <div className="grid sm:grid-cols-3 gap-3">
                <input type="text" value={edu.field_of_study} onChange={(e) => update("education", profile.education.map((x, j) => j === i ? { ...x, field_of_study: e.target.value } : x))} placeholder="Field of study" className={fieldClass} style={fieldStyle} />
                <input type="text" value={edu.start_date} onChange={(e) => update("education", profile.education.map((x, j) => j === i ? { ...x, start_date: e.target.value } : x))} placeholder="Start date" className={fieldClass} style={fieldStyle} />
                <input type="text" value={edu.end_date} onChange={(e) => update("education", profile.education.map((x, j) => j === i ? { ...x, end_date: e.target.value } : x))} placeholder="End date" className={fieldClass} style={fieldStyle} />
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() => update("education", [...profile.education, emptyEducation()])}
            className="text-sm font-medium px-4 py-2.5 rounded-xl border border-white/10 text-gray-400 hover:border-white/20 hover:text-white transition-all"
          >
            + Add another education
          </button>
        </div>
      </div>

      {/* ── Job Category ── */}
      <div className="rounded-2xl p-8 space-y-6" style={cardStyle}>
        <div>
          <h2 className="font-semibold text-white text-lg">💼 What kind of jobs are you looking for?</h2>
          <p className="text-sm text-gray-500 mt-1">This helps us fetch the right jobs and expand your skills correctly.</p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {JOB_CATEGORIES.map((cat) => (
            <button
              key={cat.value}
              type="button"
              onClick={() => {
                setOtherCategory(false);
                update("job_category", cat.value);
              }}
              className={`p-4 rounded-xl text-left transition-all border ${
                !otherCategory && profile.job_category === cat.value
                  ? "bg-blue-600/20 border-blue-500 text-white"
                  : "border-white/10 text-gray-400 hover:border-white/20 hover:text-white"
              }`}
            >
              <div className="text-2xl mb-2">{cat.icon}</div>
              <div className="text-sm font-semibold">{cat.label}</div>
            </button>
          ))}
          <button
            type="button"
            onClick={() => {
              setOtherCategory(true);
              update("job_category", "");
            }}
            className={`p-4 rounded-xl text-left transition-all border ${
              otherCategory ? "bg-blue-600/20 border-blue-500 text-white" : "border-white/10 text-gray-400 hover:border-white/20 hover:text-white"
            }`}
          >
            <div className="text-2xl mb-2">🔍</div>
            <div className="text-sm font-semibold">Other — search</div>
          </button>
        </div>
        {otherCategory && (
          <input
            type="text"
            value={profile.job_category}
            onChange={(e) => update("job_category", e.target.value)}
            placeholder="e.g. Sales Manager, DevOps Engineer, Content Writer…"
            className={fieldClass}
            style={fieldStyle}
          />
        )}

        <div>
          <label className="block text-sm text-gray-400 mb-3">Experience Level</label>
          <div className="flex flex-wrap gap-3">
            {EXP_LEVELS.map((l) => (
              <button key={l.value} type="button" onClick={() => update("experience_level", l.value)} className={chipClass(profile.experience_level === l.value)}>
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-3">Work Type</label>
          <div className="flex flex-wrap gap-3">
            {WORK_TYPES.map((w) => (
              <button key={w} type="button" onClick={() => toggleWorkType(w)} className={chipClass(profile.work_type.includes(w))}>
                {w}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Roles / Skills / Tools / Locations ── */}
      <div className="rounded-2xl p-8 space-y-6" style={cardStyle}>
        <h2 className="font-semibold text-white text-lg">🎯 Roles, Skills & Tools</h2>
        <SearchSelect
          label="Target Roles"
          values={profile.target_roles}
          onChange={(v) => update("target_roles", v)}
          apiField="roles"
          helperText="Search any job title — not limited to the categories above."
        />
        <SearchSelect
          label="Tools"
          values={profile.tools}
          onChange={(v) => update("tools", v)}
          apiField="tools"
          helperText='Our AI expands these automatically — e.g. "Figma" → Prototyping, Dev Handoff.'
        />
        <SearchSelect
          label="Skills"
          values={profile.skills}
          onChange={(v) => update("skills", v)}
          apiField="skills"
        />
        <SearchSelect
          label="Preferred Locations"
          values={profile.preferred_locations}
          onChange={(v) => update("preferred_locations", v)}
          staticOptions={LOCATIONS}
          helperText="Not in the list? Type it and hit Enter."
        />
      </div>

      {/* ── Links ── */}
      <div className="rounded-2xl p-8 space-y-4" style={cardStyle}>
        <h2 className="font-semibold text-white text-lg">🔗 Links</h2>
        <div className="grid sm:grid-cols-3 gap-4">
          <input type="url" value={profile.links.linkedin} onChange={(e) => updateLinks("linkedin", e.target.value)} placeholder="LinkedIn URL" className={fieldClass} style={fieldStyle} />
          <input type="url" value={profile.links.portfolio} onChange={(e) => updateLinks("portfolio", e.target.value)} placeholder="Portfolio URL" className={fieldClass} style={fieldStyle} />
          <input type="url" value={profile.links.github} onChange={(e) => updateLinks("github", e.target.value)} placeholder="GitHub URL" className={fieldClass} style={fieldStyle} />
        </div>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="rounded-xl px-4 py-3 text-red-400 text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)" }}>
          ⚠️ {error}
        </div>
      )}

      {/* ── Confirm ── */}
      <button
        type="button"
        disabled={!canSubmit}
        onClick={handleConfirm}
        className="w-full py-4 rounded-xl font-bold text-white text-lg transition-all disabled:opacity-50"
        style={{ background: "linear-gradient(135deg,#3b82f6,#8b5cf6)" }}
      >
        {loading ? (
          <span className="flex items-center justify-center gap-3">
            <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
            </svg>
            Saving your profile…
          </span>
        ) : (
          "Confirm & Get My First Digest →"
        )}
      </button>
      <p className="text-center text-sm text-gray-600">Free during beta · No credit card · Unsubscribe anytime</p>
    </div>
  );
}
