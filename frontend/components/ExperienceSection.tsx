"use client";

import { Plus, Trash2, ArrowRightLeft } from "lucide-react";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { MonthYearField } from "@/components/ui/MonthYearField";

export interface ExperienceEntry {
  title: string;
  company: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  bullets: string[];
}

export const emptyExperience = (): ExperienceEntry => ({
  title: "",
  company: "",
  start_date: "",
  end_date: "",
  is_current: false,
  bullets: [],
});

interface ExperienceSectionProps {
  entries: ExperienceEntry[];
  onChange: (entries: ExperienceEntry[]) => void;
  // Strategy: users can move items between Experience and Projects
  // (e.g. the parser filed a personal project as a job).
  onMoveToProjects?: (index: number) => void;
}

// Repeatable work-experience cards. Used identically whether the data came
// from a parsed resume or manual entry — one component, one shape.
export default function ExperienceSection({ entries, onChange, onMoveToProjects }: ExperienceSectionProps) {
  const update = (index: number, patch: Partial<ExperienceEntry>) => {
    onChange(entries.map((e, i) => (i === index ? { ...e, ...patch } : e)));
  };
  const remove = (index: number) => onChange(entries.filter((_, i) => i !== index));
  const add = () => onChange([...entries, emptyExperience()]);

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
              Experience {i + 1}
            </span>
            <div className="flex items-center gap-4">
              {onMoveToProjects && (
                <button
                  type="button"
                  onClick={() => onMoveToProjects(i)}
                  className="inline-flex items-center gap-1.5 text-xs font-medium transition hover:opacity-70"
                  style={{ color: "var(--text-muted)" }}
                  title="Not a job? Move it to Projects."
                >
                  <ArrowRightLeft size={14} strokeWidth={1.75} />
                  Move to Projects
                </button>
              )}
              <button
                type="button"
                onClick={() => remove(i)}
                aria-label={`Remove experience ${i + 1}`}
                className="inline-flex items-center gap-1.5 text-xs font-medium transition hover:opacity-70"
                style={{ color: "var(--coral)" }}
              >
                <Trash2 size={15} strokeWidth={1.75} />
                Remove
              </button>
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Job title">
              <Input value={entry.title} onChange={(e) => update(i, { title: e.target.value })} placeholder="Product Designer" />
            </Field>
            <Field label="Company">
              <Input value={entry.company} onChange={(e) => update(i, { company: e.target.value })} placeholder="Acme Inc." />
            </Field>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <MonthYearField label="Start date" value={entry.start_date} onChange={(v) => update(i, { start_date: v })} />
            <MonthYearField
              label="End date"
              value={entry.end_date}
              onChange={(v) => update(i, { end_date: v })}
              disabled={entry.is_current}
              placeholder="Present"
            />
          </div>

          <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "var(--text-muted)" }}>
            <input
              type="checkbox"
              checked={entry.is_current}
              onChange={(e) => update(i, { is_current: e.target.checked, end_date: e.target.checked ? "" : entry.end_date })}
              style={{ accentColor: "var(--primary)" }}
            />
            I currently work here
          </label>

          <Field label="What you did" helper="One bullet point per line.">
            <Textarea
              value={entry.bullets.join("\n")}
              onChange={(e) => update(i, { bullets: e.target.value.split("\n") })}
              placeholder={"Led the redesign of the onboarding flow\nShipped a design system used by 8 teams"}
              rows={5}
            />
          </Field>
        </div>
      ))}

      <button
        type="button"
        onClick={add}
        className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2.5 rounded-md border transition hover:bg-[var(--surface-muted)]"
        style={{ borderColor: "var(--border)", color: "var(--text)" }}
      >
        <Plus size={16} strokeWidth={2} />
        Add another experience
      </button>
    </div>
  );
}
