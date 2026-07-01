"use client";

import { Plus, Trash2 } from "lucide-react";
import { Field, Input, Textarea } from "@/components/ui/Field";

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
}

// Repeatable work-experience cards. Used identically whether the data came
// from a parsed resume or manual entry — one component, one shape.
export default function ExperienceSection({ entries, onChange }: ExperienceSectionProps) {
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
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Experience {i + 1}
            </span>
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

          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Job title">
              <Input value={entry.title} onChange={(e) => update(i, { title: e.target.value })} placeholder="Product Designer" />
            </Field>
            <Field label="Company">
              <Input value={entry.company} onChange={(e) => update(i, { company: e.target.value })} placeholder="Acme Inc." />
            </Field>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Start date">
              <Input value={entry.start_date} onChange={(e) => update(i, { start_date: e.target.value })} placeholder="Jan 2022" />
            </Field>
            <Field label="End date">
              <Input
                value={entry.is_current ? "" : entry.end_date}
                disabled={entry.is_current}
                onChange={(e) => update(i, { end_date: e.target.value })}
                placeholder={entry.is_current ? "Present" : "Dec 2023"}
                className="disabled:opacity-50"
              />
            </Field>
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
