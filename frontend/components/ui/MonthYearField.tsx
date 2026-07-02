"use client";

// Month + Year dropdown pair. Reads/writes a free-text date string so the
// stored shape and backend are unchanged and parsed-resume values still
// populate. Canonical output: "MMM YYYY" (e.g. "Jan 2022"), or "YYYY" if no
// month, or "" if nothing selected.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const CURRENT_YEAR = new Date().getFullYear();
// A few years ahead (expected grad/end dates) down to 1970.
const YEARS = Array.from({ length: CURRENT_YEAR + 5 - 1970 + 1 }, (_, i) => CURRENT_YEAR + 5 - i);

function parse(value: string): { month: string; year: string } {
  const v = (value || "").trim();
  if (!v) return { month: "", year: "" };
  const yearMatch = v.match(/\b(19|20)\d{2}\b/);
  const year = yearMatch ? yearMatch[0] : "";
  const monthMatch = MONTHS.find((m) => v.toLowerCase().includes(m.toLowerCase()));
  return { month: monthMatch || "", year };
}

function format(month: string, year: string): string {
  if (!year) return "";
  return month ? `${month} ${year}` : year;
}

const selectClass = "px-3 py-3 rounded-md text-[15px] transition";
const selectStyle = { background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" };

export function MonthYearField({
  label,
  value,
  onChange,
  disabled,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const { month, year } = parse(value);

  if (disabled) {
    return (
      <div className="space-y-1.5">
        <label className="block text-sm font-medium" style={{ color: "var(--text-muted)" }}>{label}</label>
        <div className="px-4 py-3 rounded-md text-[15px]" style={{ ...selectStyle, opacity: 0.5, color: "var(--text-muted)" }}>
          {placeholder || "Present"}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium" style={{ color: "var(--text-muted)" }}>{label}</label>
      <div className="grid grid-cols-2 gap-2">
        <select
          value={month}
          onChange={(e) => onChange(format(e.target.value, year))}
          className={selectClass}
          style={selectStyle}
          aria-label={`${label} month`}
        >
          <option value="">Month</option>
          {MONTHS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <select
          value={year}
          onChange={(e) => onChange(format(month, e.target.value))}
          className={selectClass}
          style={selectStyle}
          aria-label={`${label} year`}
        >
          <option value="">Year</option>
          {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>
    </div>
  );
}
