"use client";

import { useState } from "react";
import {
  User,
  FileText,
  Briefcase,
  GraduationCap,
  Target,
  Link as LinkIcon,
  Linkedin,
  Github,
  Globe,
  AlertTriangle,
  Plus,
  Trash2,
  Palette,
  FolderKanban,
  MonitorSmartphone,
  Server,
  Layers,
  ClipboardList,
  Brain,
  Search,
  ArrowRight,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import { API_URL } from "@/lib/api";
import type { Profile } from "@/lib/profile";
import { emptyEducation } from "@/lib/profile";
import ExperienceSection from "@/components/ExperienceSection";
import ProjectsSection from "@/components/ProjectsSection";
import SearchSelect from "@/components/SearchSelect";
import TemplatePicker from "@/components/TemplatePicker";
import ProfileStrength, { RecommendedChip } from "@/components/ProfileStrength";
import { computeProfileStrength } from "@/lib/profileStrength";
import { SectionCard } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { MonthYearField } from "@/components/ui/MonthYearField";
import { Button } from "@/components/ui/Button";
import SearchInput from "@/components/SearchInput";

interface ProfileEditorProps {
  initialProfile: Profile;
  resumeFilePath: string | null;
  onConfirmed: (id: string, name: string, dashboardToken: string) => void;
}

const JOB_CATEGORIES: { value: string; label: string; icon: LucideIcon }[] = [
  { value: "ui_ux_designer", label: "UI/UX Designer", icon: Palette },
  { value: "frontend_developer", label: "Frontend Developer", icon: MonitorSmartphone },
  { value: "backend_developer", label: "Backend Developer", icon: Server },
  { value: "fullstack_developer", label: "Fullstack Developer", icon: Layers },
  { value: "product_manager", label: "Product Manager", icon: ClipboardList },
  { value: "data_scientist", label: "Data Scientist / ML", icon: Brain },
];

const LOCATIONS = ["Remote", "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Anywhere in India"];
const EXP_LEVELS = [
  { value: "fresher", label: "Fresher (0–1 yr)" },
  { value: "junior", label: "Junior (1–3 yrs)" },
  { value: "mid", label: "Mid (3–5 yrs)" },
  { value: "senior", label: "Senior (5+ yrs)" },
];
const WORK_TYPES = ["Remote", "Onsite", "Hybrid"];

const chipButton = (active: boolean) =>
  `cursor-pointer px-4 py-2 rounded-md text-sm font-medium transition border ${
    active
      ? "bg-[#FEF3C7] border-[var(--primary)] text-[#B45309]"
      : "border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--primary)] hover:text-[var(--text)]"
  }`;

export default function ProfileEditor({ initialProfile, resumeFilePath, onConfirmed }: ProfileEditorProps) {
  const [profile, setProfile] = useState<Profile>(initialProfile);
  const [otherCategory, setOtherCategory] = useState(
    !!initialProfile.job_category && !JOB_CATEGORIES.some((c) => c.value === initialProfile.job_category)
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

  const canSubmit = !!profile.basic_info.full_name.trim() && !!profile.basic_info.email.trim() && !loading;

  // Strategy: users can move items between Projects and Experience — e.g.
  // the parser filed a personal project as a job (or the reverse). Convert
  // the shape, drop nothing the user typed.
  const moveExperienceToProjects = (index: number) => {
    const exp = profile.work_experience[index];
    if (!exp) return;
    setProfile((p) => ({
      ...p,
      work_experience: p.work_experience.filter((_, i) => i !== index),
      projects: [
        ...p.projects,
        {
          name: exp.company || exp.title,
          project_type: "personal",
          role: exp.title,
          description: (exp.bullets || []).filter(Boolean).join("\n"),
          technologies: [],
          url: "",
          github: "",
        },
      ],
    }));
  };

  const moveProjectToExperience = (index: number) => {
    const proj = profile.projects[index];
    if (!proj) return;
    setProfile((p) => ({
      ...p,
      projects: p.projects.filter((_, i) => i !== index),
      work_experience: [
        ...p.work_experience,
        {
          title: proj.role || proj.name,
          company: proj.name,
          start_date: "",
          end_date: "",
          is_current: false,
          bullets: proj.description ? proj.description.split("\n").filter(Boolean) : [],
        },
      ],
    }));
  };

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
      onConfirmed(data.id, profile.basic_info.full_name, data.dashboard_token || "");
    } catch (e: any) {
      setError(e.message || "Something went wrong. Please try again.");
      setLoading(false);
    }
  };

  const strength = computeProfileStrength(profile, !!resumeFilePath);

  return (
    <div className="space-y-6">
      <p className="text-center" style={{ color: "var(--text-muted)" }}>
        Here&apos;s what we found in your resume. Double-check everything looks right, then confirm.
      </p>

      {/* Live strength meter — updates as sections are filled in. */}
      <ProfileStrength strength={strength} />

      {/* Basic Info */}
      <SectionCard icon={User} title="Basic Info">
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Full name" required>
            <Input value={profile.basic_info.full_name} onChange={(e) => updateBasic("full_name", e.target.value)} placeholder="Gargey Patel" />
          </Field>
          <Field label="Email" required>
            <Input type="email" value={profile.basic_info.email} onChange={(e) => updateBasic("email", e.target.value)} placeholder="you@gmail.com" />
          </Field>
          <Field label="Phone" error={flag("phone") ? "We couldn't find a phone number — add one?" : undefined}>
            <Input type="tel" value={profile.basic_info.phone} onChange={(e) => updateBasic("phone", e.target.value)} placeholder="+91 99254 77017" />
          </Field>
          <Field label="Location">
            <Input value={profile.basic_info.location} onChange={(e) => updateBasic("location", e.target.value)} placeholder="Mumbai, India" />
          </Field>
        </div>
      </SectionCard>

      {/* Summary */}
      <SectionCard icon={FileText} title="Summary" action={<RecommendedChip />}>
        <Field label="Professional summary" error={flag("summary") ? "We're not fully confident in this — worth a quick edit." : undefined}>
          <Textarea value={profile.summary} onChange={(e) => update("summary", e.target.value)} rows={6} placeholder="A short professional summary…" />
        </Field>
      </SectionCard>

      {/* Work Experience */}
      <SectionCard icon={Briefcase} title="Work Experience" action={<RecommendedChip />}>
        <p className="text-sm -mt-3 mb-4" style={{ color: "var(--text-muted)" }}>
          Professional work only — full-time, part-time, internships, freelance. Personal projects go in the next section.
        </p>
        <ExperienceSection
          entries={profile.work_experience}
          onChange={(v) => update("work_experience", v)}
          onMoveToProjects={moveExperienceToProjects}
        />
      </SectionCard>

      {/* Projects */}
      <SectionCard icon={FolderKanban} title="Projects" action={<RecommendedChip />}>
        <p className="text-sm -mt-3 mb-4" style={{ color: "var(--text-muted)" }}>
          Personal, academic, freelance, or open-source work. Especially valuable for students and early-career professionals.
        </p>
        <ProjectsSection
          entries={profile.projects}
          onChange={(v) => update("projects", v)}
          onMoveToExperience={moveProjectToExperience}
        />
      </SectionCard>

      {/* Education */}
      <SectionCard icon={GraduationCap} title="Education" action={<RecommendedChip />}>
        <div className="space-y-4">
          {profile.education.map((edu, i) => (
            <div key={i} className="rounded-md p-5 space-y-4" style={{ background: "var(--surface-muted)", border: "1px solid var(--border)" }}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>Education {i + 1}</span>
                <button
                  type="button"
                  onClick={() => update("education", profile.education.filter((_, j) => j !== i))}
                  aria-label={`Remove education ${i + 1}`}
                  className="inline-flex items-center gap-1.5 text-xs font-medium transition hover:opacity-70"
                  style={{ color: "var(--coral)" }}
                >
                  <Trash2 size={15} strokeWidth={1.75} />
                  Remove
                </button>
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <Field label="School">
                  <Input value={edu.school} onChange={(e) => update("education", profile.education.map((x, j) => (j === i ? { ...x, school: e.target.value } : x)))} placeholder="NIT Surat" />
                </Field>
                <Field label="Degree">
                  <Input value={edu.degree} onChange={(e) => update("education", profile.education.map((x, j) => (j === i ? { ...x, degree: e.target.value } : x)))} placeholder="B.Tech" />
                </Field>
              </div>
              <div className="grid sm:grid-cols-3 gap-4">
                <Field label="Field of study">
                  <Input value={edu.field_of_study} onChange={(e) => update("education", profile.education.map((x, j) => (j === i ? { ...x, field_of_study: e.target.value } : x)))} placeholder="Computer Science" />
                </Field>
                <MonthYearField label="Start" value={edu.start_date} onChange={(v) => update("education", profile.education.map((x, j) => (j === i ? { ...x, start_date: v } : x)))} />
                <MonthYearField label="End" value={edu.end_date} onChange={(v) => update("education", profile.education.map((x, j) => (j === i ? { ...x, end_date: v } : x)))} />
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() => update("education", [...profile.education, emptyEducation()])}
            className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2.5 rounded-md border transition hover:bg-[var(--surface-muted)]"
            style={{ borderColor: "var(--border)", color: "var(--text)" }}
          >
            <Plus size={16} strokeWidth={2} />
            Add another education
          </button>
        </div>
      </SectionCard>

      {/* Job Category */}
      <SectionCard icon={Briefcase} title="What kind of jobs are you looking for?">
        <p className="text-sm -mt-3 mb-4" style={{ color: "var(--text-muted)" }}>
          This helps us fetch the right jobs and expand your skills correctly.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {JOB_CATEGORIES.map((cat) => {
            const active = !otherCategory && profile.job_category === cat.value;
            return (
              <button
                key={cat.value}
                type="button"
                onClick={() => {
                  setOtherCategory(false);
                  update("job_category", cat.value);
                }}
                className={`p-4 rounded-md text-left transition border ${
                  active ? "bg-[#FEF3C7] border-[var(--primary)]" : "border-[var(--border)] hover:border-[var(--primary)]"
                }`}
              >
                <cat.icon size={22} strokeWidth={1.75} style={{ color: active ? "var(--primary)" : "var(--text-muted)" }} />
                <div className="text-sm font-semibold mt-2" style={{ color: "var(--text)" }}>{cat.label}</div>
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => {
              setOtherCategory(true);
              update("job_category", "");
            }}
            className={`p-4 rounded-md text-left transition border ${
              otherCategory ? "bg-[#FEF3C7] border-[var(--primary)]" : "border-[var(--border)] hover:border-[var(--primary)]"
            }`}
          >
            <Search size={22} strokeWidth={1.75} style={{ color: otherCategory ? "var(--primary)" : "var(--text-muted)" }} />
            <div className="text-sm font-semibold mt-2" style={{ color: "var(--text)" }}>Other — search</div>
          </button>
        </div>

        {otherCategory && (
          <div className="mt-4">
            <SearchInput
              label="Your role"
              value={profile.job_category}
              onChange={(v) => update("job_category", v)}
              apiField="roles"
              placeholder="e.g. DevOps Engineer, Content Writer…"
              helperText="Start typing — pick a suggestion or enter your own."
            />
          </div>
        )}

        <div className="mt-6 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2" style={{ color: "var(--text-muted)" }}>Experience level</label>
            <div className="flex flex-wrap gap-2.5">
              {EXP_LEVELS.map((l) => (
                <button key={l.value} type="button" onClick={() => update("experience_level", l.value)} className={chipButton(profile.experience_level === l.value)}>
                  {l.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2" style={{ color: "var(--text-muted)" }}>Work type</label>
            <div className="flex flex-wrap gap-2.5">
              {WORK_TYPES.map((w) => (
                <button key={w} type="button" onClick={() => toggleWorkType(w)} className={chipButton(profile.work_type.includes(w))}>
                  {w}
                </button>
              ))}
            </div>
          </div>
        </div>
      </SectionCard>

      {/* Roles / Skills / Tools / Locations */}
      <SectionCard icon={Target} title="Roles, Skills & Tools" action={<RecommendedChip />}>
        <div className="space-y-6">
          <SearchSelect label="Target roles" values={profile.target_roles} onChange={(v) => update("target_roles", v)} apiField="roles" helperText="Search any job title — not limited to the categories above." />
          <SearchSelect label="Tools" values={profile.tools} onChange={(v) => update("tools", v)} apiField="tools" helperText='Our AI expands these — e.g. "Figma" → Prototyping, Dev Handoff.' />
          <SearchSelect label="Skills" values={profile.skills} onChange={(v) => update("skills", v)} apiField="skills" />
          <SearchSelect label="Preferred locations" values={profile.preferred_locations} onChange={(v) => update("preferred_locations", v)} staticOptions={LOCATIONS} helperText="Not in the list? Type it and hit Enter." />
        </div>
      </SectionCard>

      {/* Resume style */}
      <SectionCard icon={FileText} title="Resume style">
        <p className="text-sm -mt-3 mb-4" style={{ color: "var(--text-muted)" }}>
          Pick how your tailored resumes will look. You can change this anytime.
        </p>
        <TemplatePicker
          value={profile.resume_template || "professional"}
          onChange={(v) => update("resume_template", v)}
        />
      </SectionCard>

      {/* Links */}
      <SectionCard icon={LinkIcon} title="Links" action={<RecommendedChip />}>
        <div className="space-y-4">
          <Field label="LinkedIn">
            <div className="relative">
              <Linkedin size={18} strokeWidth={1.75} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--text-muted)" }} />
              <Input value={profile.links.linkedin} onChange={(e) => updateLinks("linkedin", e.target.value)} placeholder="https://linkedin.com/in/you" className="pl-10" />
            </div>
          </Field>
          <Field label="Portfolio">
            <div className="relative">
              <Globe size={18} strokeWidth={1.75} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--text-muted)" }} />
              <Input value={profile.links.portfolio} onChange={(e) => updateLinks("portfolio", e.target.value)} placeholder="https://your-site.com" className="pl-10" />
            </div>
          </Field>
          <Field label="GitHub">
            <div className="relative">
              <Github size={18} strokeWidth={1.75} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--text-muted)" }} />
              <Input value={profile.links.github} onChange={(e) => updateLinks("github", e.target.value)} placeholder="https://github.com/you" className="pl-10" />
            </div>
          </Field>
        </div>
      </SectionCard>

      {error && (
        <div className="rounded-md px-4 py-3 text-sm flex items-start gap-2" style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "var(--coral)" }}>
          <AlertTriangle size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <Button variant="primary" size="lg" disabled={!canSubmit} onClick={handleConfirm} className="w-full">
        {loading ? (
          <>
            <Loader2 size={18} className="animate-spin" />
            Saving your profile…
          </>
        ) : (
          <>
            Confirm &amp; Find My Matches
            <ArrowRight size={18} strokeWidth={2} />
          </>
        )}
      </Button>
      <p className="text-center text-sm" style={{ color: "var(--text-muted)" }}>
        Free during beta · No credit card · Unsubscribe anytime
      </p>
    </div>
  );
}
