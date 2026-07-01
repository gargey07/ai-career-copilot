"use client";

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

const fieldClass =
  "w-full px-4 py-2.5 rounded-xl text-white placeholder-gray-600 text-sm transition";
const fieldStyle = { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" };

// Repeatable work-experience cards. Used identically whether the data
// came from a parsed resume or manual entry — one component, one shape.
export default function ExperienceSection({ entries, onChange }: ExperienceSectionProps) {
  const update = (index: number, patch: Partial<ExperienceEntry>) => {
    const next = entries.map((e, i) => (i === index ? { ...e, ...patch } : e));
    onChange(next);
  };

  const remove = (index: number) => onChange(entries.filter((_, i) => i !== index));

  const add = () => onChange([...entries, emptyExperience()]);

  return (
    <div className="space-y-4">
      {entries.map((entry, i) => (
        <div
          key={i}
          className="rounded-xl p-5 space-y-3"
          style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}
        >
          <div className="flex justify-between items-start gap-3">
            <div className="grid sm:grid-cols-2 gap-3 flex-1">
              <input
                type="text"
                value={entry.title}
                onChange={(e) => update(i, { title: e.target.value })}
                placeholder="Job title"
                className={fieldClass}
                style={fieldStyle}
              />
              <input
                type="text"
                value={entry.company}
                onChange={(e) => update(i, { company: e.target.value })}
                placeholder="Company"
                className={fieldClass}
                style={fieldStyle}
              />
            </div>
            <button
              type="button"
              onClick={() => remove(i)}
              className="text-gray-500 hover:text-red-400 transition-colors text-sm px-2 py-2"
              aria-label="Remove experience"
            >
              Remove
            </button>
          </div>

          <div className="grid sm:grid-cols-2 gap-3 items-center">
            <input
              type="text"
              value={entry.start_date}
              onChange={(e) => update(i, { start_date: e.target.value })}
              placeholder="Start date (e.g. Jan 2022)"
              className={fieldClass}
              style={fieldStyle}
            />
            <div className="flex items-center gap-3">
              <input
                type="text"
                value={entry.is_current ? "" : entry.end_date}
                disabled={entry.is_current}
                onChange={(e) => update(i, { end_date: e.target.value })}
                placeholder={entry.is_current ? "Present" : "End date"}
                className={`${fieldClass} disabled:opacity-50`}
                style={fieldStyle}
              />
              <label className="flex items-center gap-2 text-xs text-gray-400 whitespace-nowrap">
                <input
                  type="checkbox"
                  checked={entry.is_current}
                  onChange={(e) => update(i, { is_current: e.target.checked, end_date: e.target.checked ? "" : entry.end_date })}
                />
                Current role
              </label>
            </div>
          </div>

          <textarea
            value={entry.bullets.join("\n")}
            onChange={(e) => update(i, { bullets: e.target.value.split("\n") })}
            placeholder={"Describe this role — one bullet point per line"}
            rows={3}
            className={`${fieldClass} font-mono resize-none`}
            style={fieldStyle}
          />
        </div>
      ))}

      <button
        type="button"
        onClick={add}
        className="text-sm font-medium px-4 py-2.5 rounded-xl border border-white/10 text-gray-400 hover:border-white/20 hover:text-white transition-all"
      >
        + Add another experience
      </button>
    </div>
  );
}
