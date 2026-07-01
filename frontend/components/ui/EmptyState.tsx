"use client";

import { ReactNode } from "react";
import { LucideIcon } from "lucide-react";

// Icon + headline + one sentence + optional single action.
// See docs/design-system.md §12.
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="text-center py-16 px-6 animate-fade-in">
      {Icon && (
        <div
          className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full"
          style={{ background: "var(--surface-muted)" }}
        >
          <Icon size={24} strokeWidth={1.75} style={{ color: "var(--text-muted)" }} />
        </div>
      )}
      <h3 className="text-lg font-semibold" style={{ color: "var(--text)" }}>
        {title}
      </h3>
      {description && (
        <p className="mt-1.5 text-sm max-w-sm mx-auto" style={{ color: "var(--text-muted)" }}>
          {description}
        </p>
      )}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}
