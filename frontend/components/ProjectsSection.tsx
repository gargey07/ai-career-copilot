"use client";

import { Plus, Trash2, ArrowRightLeft } from "lucide-react";
import { Field, Input, Textarea } from "@/components/ui/Field";
import SearchSelect from "@/components/SearchSelect";
import { emptyProject, type ProjectEntry } from "@/lib/profile";

// Projects are NOT work experience — own section, own shape
// (docs/PRODUCT_STRATEGY_BETA.md). Same repeatable-card pattern as
// ExperienceSection so parsed and manual entries look identical.

const PROJECT_TYPES: { value: string; label: string }[] = [
  { value: "personal", label: "Personal" },
  { value: "academic", label: "Academic" },
  { value: "freelance", label: "Freelance" },
  { value: "research", label: "Research" },
  { value: "open_source", label: "Open Source" },
  { value: "capstone", label: "Capstone" },
];

interface ProjectsSectionProps {
  entries: ProjectEntry[];
  onChange: (entries: ProjectEntry[]) => void;
  // Strategy: users can move items between Projects and Experience.
  onMoveToExperience?: (index: number) => void;
}

export default function ProjectsSection({ entries, onChange, onMoveToExperience }: ProjectsSectionProps) {
  const update = (index: number, patch: Partial<ProjectEntry>) => {
    onChange(entries.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  };
  const remove = (index: number) => onChange(entries.filter((_, i) => i !== index));
  const add = () => onChange([...entries, emptyProject()]);

  return (
    <div className="space-y-4">
      {entries.map((entry, i) => (
        <div
          key={i}
          className="rounded-md p-5 space-y-4"
          style={{ background: "var(--surface-muted)", border: "1px solid var(--border)" }}
        >
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Project {i + 1}
            </span>
            <div className="flex items-center gap-4">
              {onMoveToExperience && (
                <button
                  type="button"
                  onClick={() => onMoveToExperience(i)}
                  className="inline-flex items-center gap-1.5 text-xs font-medium transition hover:opacity-70"
                  style={{ color: "var(--text-muted)" }}
                  title="This was actually a job? Move it to Work Experience."
                >
                  <ArrowRightLeft size={14} strokeWidth={1.75} />
                  Move to Experience
                </button>
              )}
              <button
                type="button"
                onClick={() => remove(i)}
                aria-label={`Remove project ${i + 1}`}
                className="inline-flex items-center gap-1.5 text-xs font-medium transition hover:opacity-70"
                style={{ color: "var(--coral)" }}
              >
                <Trash2 size={15} strokeWidth={1.75} />
                Remove
              </button>
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Project name">
              <Input value={entry.name} onChange={(e) => update(i, { name: e.target.value })} placeholder="FuelBite — food delivery app" />
            </Field>
            <Field label="Your role">
              <Input value={entry.role} onChange={(e) => update(i, { role: e.target.value })} placeholder="Designer & builder" />
            </Field>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2" style={{ color: "var(--text-muted)" }}>Project type</label>
            <div className="flex flex-wrap gap-2">
              {PROJECT_TYPES.map((t) => {
                const active = entry.project_type === t.value;
                return (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => update(i, { project_type: t.value })}
                    className={`cursor-pointer px-3 py-1.5 rounded-md text-xs font-medium transition border ${
                      active
                        ? "bg-[#FEF3C7] border-[var(--primary)] text-[#B45309]"
                        : "border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--primary)] hover:text-[var(--text)]"
                    }`}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>
          </div>

          <Field label="What it is & what you did" helper="Impact and responsibilities — recruiters read this first.">
            <Textarea
              value={entry.description}
              onChange={(e) => update(i, { description: e.target.value })}
              placeholder="Designed and shipped a food-delivery concept app; ran usability tests with 12 students and iterated the checkout flow."
              rows={3}
            />
          </Field>

          <SearchSelect
            label="Technologies"
            values={entry.technologies}
            onChange={(v) => update(i, { technologies: v })}
            apiField="tools"
            helperText="The tools and tech this project used."
          />

          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Project URL">
              <Input value={entry.url} onChange={(e) => update(i, { url: e.target.value })} placeholder="https://…" />
            </Field>
            <Field label="GitHub">
              <Input value={entry.github} onChange={(e) => update(i, { github: e.target.value })} placeholder="https://github.com/…" />
            </Field>
          </div>
        </div>
      ))}

      <button
        type="button"
        onClick={add}
        className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2.5 rounded-md border transition hover:bg-[var(--surface-muted)]"
        style={{ borderColor: "var(--border)", color: "var(--text)" }}
      >
        <Plus size={16} strokeWidth={2} />
        Add a project
      </button>
    </div>
  );
}
