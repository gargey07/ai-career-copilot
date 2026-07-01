"use client";

import { HTMLAttributes, ReactNode } from "react";
import { LucideIcon } from "lucide-react";

// White surface, hairline border, soft shadow. See docs/design-system.md §11.
export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={`bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-e1 ${className}`}
    />
  );
}

export function SectionCard({
  icon: Icon,
  title,
  action,
  children,
  className = "",
}: {
  icon?: LucideIcon;
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={`p-6 sm:p-8 ${className}`}>
      {(title || Icon) && (
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2.5">
            {Icon && <Icon size={20} strokeWidth={1.75} style={{ color: "var(--primary)" }} />}
            {title && (
              <h2 className="text-lg font-semibold" style={{ color: "var(--text)" }}>
                {title}
              </h2>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </Card>
  );
}
