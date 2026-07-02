"use client";

import { useState } from "react";
import { Sparkles, Check, ChevronDown, ChevronUp } from "lucide-react";
import type { ProfileStrengthResult } from "@/lib/profileStrength";

// Progress, not punishment: a strength meter with completed ✓ and pending ○
// lists. Every pending item explains WHY it's worth doing — the encouragement
// pattern from the product strategy. Never says "required".

function barColor(percent: number): string {
  if (percent >= 80) return "var(--success)";
  if (percent >= 50) return "var(--primary)";
  return "var(--accent)";
}

export default function ProfileStrength({ strength }: { strength: ProfileStrengthResult }) {
  const [expanded, setExpanded] = useState(false);
  const { percent, completed, pending } = strength;

  return (
    <div className="rounded-lg p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-e1)" }}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Sparkles size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
          <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>Profile Strength</span>
        </div>
        <span className="text-lg font-extrabold tabular-nums" style={{ color: barColor(percent) }}>{percent}%</span>
      </div>

      <div className="mt-3 h-2 rounded-full overflow-hidden" style={{ background: "var(--surface-muted)" }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${percent}%`, background: barColor(percent) }}
        />
      </div>

      {pending.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium transition hover:opacity-70"
            style={{ color: "var(--text-muted)" }}
          >
            {expanded ? <ChevronUp size={14} strokeWidth={2} /> : <ChevronDown size={14} strokeWidth={2} />}
            {expanded ? "Hide suggestions" : `${pending.length} way${pending.length > 1 ? "s" : ""} to strengthen your profile`}
          </button>

          {expanded && (
            <div className="mt-4 space-y-4">
              {completed.length > 0 && (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>
                    Completed
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {completed.map((i) => (
                      <span
                        key={i.key}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
                        style={{ background: "#ECFDF5", color: "var(--success)" }}
                      >
                        <Check size={12} strokeWidth={2.5} />
                        {i.label}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>
                  Recommended
                </div>
                <ul className="space-y-2.5">
                  {pending.map((i) => (
                    <li key={i.key} className="flex items-start gap-2.5">
                      <span
                        className="mt-0.5 h-4 w-4 rounded-full shrink-0"
                        style={{ border: "1.5px solid var(--border)" }}
                        aria-hidden="true"
                      />
                      <span className="text-sm leading-snug">
                        <span className="font-medium" style={{ color: "var(--text)" }}>{i.label}</span>{" "}
                        <span style={{ color: "var(--text-muted)" }}>— {i.why}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Small header chip for optional sections: "Recommended", never "Required".
export function RecommendedChip() {
  return (
    <span
      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
      style={{ background: "#FEF3C7", color: "#B45309", border: "1px solid #FDE68A" }}
    >
      <Sparkles size={12} strokeWidth={2} />
      Recommended
    </span>
  );
}
