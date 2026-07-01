"use client";

import { X } from "lucide-react";

// Selected-value chip (amber tint). See docs/design-system.md §2 / §9.
export function Chip({ label, onRemove }: { label: string; onRemove?: () => void }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-sm font-medium"
      style={{ background: "#FEF3C7", border: "1px solid var(--primary)", color: "#B45309" }}
    >
      {label}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${label}`}
          className="hover:opacity-60 transition"
          style={{ color: "#B45309" }}
        >
          <X size={14} strokeWidth={2} />
        </button>
      )}
    </span>
  );
}
