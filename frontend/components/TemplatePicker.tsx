"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Eye, X } from "lucide-react";
import { API_URL } from "@/lib/api";
import type { Profile } from "@/lib/profile";

// Visual picker for the PDF resume design. Each option shows a tiny
// CSS-drawn mock of the real template's layout — no screenshots to
// maintain, always in sync with a redesign by hand.

export const TEMPLATE_OPTIONS = [
  {
    value: "professional",
    label: "Professional",
    desc: "The classic single-column format recruiters know best. Most ATS-friendly.",
  },
  {
    value: "modern",
    label: "Modern",
    desc: "Bold dark header. Stands out in creative & tech roles.",
  },
  {
    value: "classic",
    label: "Classic",
    desc: "Traditional serif. The safe pick for corporate & formal roles.",
  },
  {
    value: "minimal",
    label: "Minimal",
    desc: "Clean with an amber accent. Compact — fits more on one page.",
  },
] as const;

// Shared preview scaffolding: a small "page" with fake text lines.
function Line({ w, c = "#CBD5E1", h = 3 }: { w: string; c?: string; h?: number }) {
  return <div style={{ width: w, height: h, background: c, borderRadius: 2 }} />;
}

function ModernPreview() {
  return (
    <div className="w-full h-full flex flex-col overflow-hidden rounded" style={{ background: "#fff" }}>
      <div className="px-2 py-2 space-y-1" style={{ background: "#302b63" }}>
        <Line w="55%" c="rgba(255,255,255,0.95)" h={4} />
        <Line w="35%" c="rgba(255,255,255,0.5)" />
      </div>
      <div className="px-2 py-2 space-y-1.5 flex-1">
        <Line w="30%" c="#302b63" />
        <Line w="90%" />
        <Line w="80%" />
        <Line w="28%" c="#302b63" />
        <Line w="85%" />
      </div>
    </div>
  );
}

function ClassicPreview() {
  return (
    <div className="w-full h-full flex flex-col overflow-hidden rounded px-2 py-2" style={{ background: "#fff" }}>
      <div className="flex flex-col items-center space-y-1 pb-1.5 mb-1.5" style={{ borderBottom: "1.5px solid #111" }}>
        <Line w="45%" c="#111" h={4} />
        <Line w="30%" c="#94A3B8" />
      </div>
      <div className="space-y-1.5 flex-1">
        <Line w="35%" c="#111" />
        <Line w="90%" />
        <Line w="82%" />
        <Line w="30%" c="#111" />
        <Line w="88%" />
      </div>
    </div>
  );
}

function MinimalPreview() {
  return (
    <div className="w-full h-full flex overflow-hidden rounded px-2 py-2 gap-1.5" style={{ background: "#fff" }}>
      <div style={{ width: 3, background: "#F59E0B", borderRadius: 2, height: "35%" }} />
      <div className="flex-1 space-y-1.5">
        <Line w="50%" c="#0F2F3A" h={4} />
        <Line w="32%" c="#F59E0B" />
        <Line w="90%" />
        <Line w="84%" />
        <Line w="26%" c="#F59E0B" />
        <Line w="80%" />
      </div>
    </div>
  );
}

function ProfessionalPreview() {
  // Jake's-Resume look: name left + contact right, small-caps ruled sections.
  return (
    <div className="w-full h-full flex flex-col overflow-hidden rounded px-2 py-2" style={{ background: "#fff" }}>
      <div className="flex justify-between items-start mb-1.5">
        <Line w="40%" c="#111" h={5} />
        <div className="space-y-1 flex flex-col items-end" style={{ width: "30%" }}>
          <Line w="100%" c="#94A3B8" h={2} />
          <Line w="70%" c="#94A3B8" h={2} />
        </div>
      </div>
      <div className="space-y-1.5 flex-1">
        <div className="pb-0.5" style={{ borderBottom: "1px solid #111", width: "100%" }}>
          <Line w="28%" c="#111" />
        </div>
        <Line w="92%" />
        <Line w="85%" />
        <div className="pb-0.5 pt-0.5" style={{ borderBottom: "1px solid #111", width: "100%" }}>
          <Line w="32%" c="#111" />
        </div>
        <Line w="88%" />
      </div>
    </div>
  );
}

const PREVIEWS: Record<string, () => JSX.Element> = {
  professional: ProfessionalPreview,
  modern: ModernPreview,
  classic: ClassicPreview,
  minimal: MinimalPreview,
};

// Builds the /api/resumes/preview request body from the in-progress
// onboarding profile — same shape the backend's ResumePreviewRequest
// expects (a subset of the confirm payload, all optional there).
function previewPayload(profile: Profile, templateName: string) {
  return {
    basic_info: profile.basic_info,
    summary: profile.summary,
    work_experience: profile.work_experience,
    projects: profile.projects,
    education: profile.education,
    target_roles: profile.target_roles,
    skills: profile.skills,
    tools: profile.tools,
    links: profile.links,
    job_category: profile.job_category,
    template_name: templateName,
  };
}

// ── Real-data preview modal — tabs across all 4 styles, one fetch per tab ──────
function PreviewModal({ profile, initialTemplate, onClose, onUse }: {
  profile: Profile;
  initialTemplate: string;
  onClose: () => void;
  onUse: (templateName: string) => void;
}) {
  const [activeTemplate, setActiveTemplate] = useState(initialTemplate);
  const [html, setHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const cacheRef = useRef<Record<string, string>>({});

  const load = async (templateName: string) => {
    setActiveTemplate(templateName);
    if (cacheRef.current[templateName]) {
      setHtml(cacheRef.current[templateName]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/resumes/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(previewPayload(profile, templateName)),
      });
      if (!res.ok) throw new Error("Couldn't load the preview.");
      const text = await res.text();
      cacheRef.current[templateName] = text;
      setHtml(text);
    } catch {
      setError("Couldn't load the preview — try again in a moment.");
    } finally {
      setLoading(false);
    }
  };

  // Fetch the initial tab once, on mount.
  useEffect(() => {
    load(initialTemplate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(15,47,58,0.55)" }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Resume preview"
    >
      <div
        className="w-full max-w-3xl rounded-lg overflow-hidden flex flex-col"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", maxHeight: "90vh" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="flex gap-1.5">
            {TEMPLATE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => load(opt.value)}
                className="px-3 py-1.5 rounded-md text-xs font-semibold transition"
                style={
                  activeTemplate === opt.value
                    ? { background: "#FEF3C7", color: "#B45309" }
                    : { color: "var(--text-muted)" }
                }
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button type="button" onClick={onClose} aria-label="Close preview" className="p-1 rounded hover:bg-[var(--surface-muted)]">
            <X size={18} strokeWidth={1.75} style={{ color: "var(--text-muted)" }} />
          </button>
        </div>

        <div className="flex-1 overflow-auto" style={{ background: "#525659" }}>
          {loading ? (
            <p className="text-sm text-center py-16" style={{ color: "#fff" }}>Rendering your resume…</p>
          ) : error ? (
            <p className="text-sm text-center py-16" style={{ color: "#FCA5A5" }}>{error}</p>
          ) : html ? (
            <iframe title="Resume preview" srcDoc={html} className="w-full" style={{ minHeight: "70vh", border: "none", background: "#fff" }} />
          ) : null}
        </div>

        <div className="flex items-center justify-between px-5 py-3" style={{ borderTop: "1px solid var(--border)" }}>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            Filled with your real info as you&apos;ve entered it so far.
          </p>
          <button
            type="button"
            onClick={() => onUse(activeTemplate)}
            className="px-4 py-2 rounded-md text-sm font-semibold text-white transition hover:opacity-90"
            style={{ background: "var(--primary)" }}
          >
            Use this style
          </button>
        </div>
      </div>
    </div>
  );
}

interface TemplatePickerProps {
  value: string;
  onChange: (value: string) => void;
  profile: Profile;
}

export default function TemplatePicker({ value, onChange, profile }: TemplatePickerProps) {
  const [previewing, setPreviewing] = useState(false);

  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {TEMPLATE_OPTIONS.map((opt) => {
          const active = value === opt.value;
          const Preview = PREVIEWS[opt.value];
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange(opt.value)}
              aria-pressed={active}
              className={`relative p-3 rounded-md text-left transition border ${
                active ? "bg-[#FEF3C7] border-[var(--primary)]" : "border-[var(--border)] hover:border-[var(--primary)]"
              }`}
            >
              {active && (
                <span
                  className="absolute top-2 right-2 flex h-5 w-5 items-center justify-center rounded-full"
                  style={{ background: "var(--primary)" }}
                >
                  <Check size={12} strokeWidth={3} color="#fff" />
                </span>
              )}
              <div
                className="h-28 mb-3 rounded overflow-hidden"
                style={{ border: "1px solid var(--border)", boxShadow: "var(--shadow-e1)" }}
              >
                <Preview />
              </div>
              <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>{opt.label}</div>
              <div className="text-xs mt-0.5 leading-relaxed" style={{ color: "var(--text-muted)" }}>{opt.desc}</div>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        onClick={() => setPreviewing(true)}
        className="mt-3 inline-flex items-center gap-2 text-sm font-medium hover:underline"
        style={{ color: "var(--primary)" }}
      >
        <Eye size={16} strokeWidth={1.75} />
        Preview with your info
      </button>

      {previewing && (
        <PreviewModal
          profile={profile}
          initialTemplate={value || "professional"}
          onClose={() => setPreviewing(false)}
          onUse={(templateName) => {
            onChange(templateName);
            setPreviewing(false);
          }}
        />
      )}
    </div>
  );
}
