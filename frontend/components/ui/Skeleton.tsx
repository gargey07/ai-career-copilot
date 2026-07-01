"use client";

import { CSSProperties } from "react";

// Shimmer block — the standard loading state (never a spinner).
// See docs/design-system.md §12.
export function Skeleton({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />;
}
