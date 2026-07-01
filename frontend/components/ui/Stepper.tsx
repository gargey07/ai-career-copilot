"use client";

import { Check } from "lucide-react";

export type StepState = "done" | "active" | "pending" | "error";
export interface Step {
  label: string;
  state: StepState;
}

// Horizontal progress steps for long async flows (e.g. resume parsing:
// Uploaded → AI Parsed → Verified → Ready). See docs/design-system.md §12.
function circleStyle(state: StepState) {
  switch (state) {
    case "done":
    case "active":
      return { background: "var(--primary)", color: "#fff", border: "1px solid var(--primary)" };
    case "error":
      return { background: "var(--coral)", color: "#fff", border: "1px solid var(--coral)" };
    default:
      return { background: "var(--surface)", color: "var(--text-muted)", border: "1px solid var(--border)" };
  }
}

function labelColor(state: StepState) {
  if (state === "pending") return "var(--text-muted)";
  if (state === "error") return "var(--coral)";
  return "var(--text)";
}

export function Stepper({ steps }: { steps: Step[] }) {
  return (
    <div className="flex items-start w-full">
      {steps.map((s, i) => (
        <div key={s.label} className="flex items-start flex-1 last:flex-none">
          <div className="flex flex-col items-center gap-1.5">
            <div
              className="flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold transition"
              style={circleStyle(s.state)}
            >
              {s.state === "done" ? <Check size={14} strokeWidth={2.5} /> : i + 1}
            </div>
            <span
              className="text-[11px] font-medium whitespace-nowrap"
              style={{ color: labelColor(s.state) }}
            >
              {s.label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div
              className="h-0.5 flex-1 mx-1.5 mt-3.5 rounded-full transition"
              style={{ background: s.state === "done" ? "var(--primary)" : "var(--border)" }}
            />
          )}
        </div>
      ))}
    </div>
  );
}
