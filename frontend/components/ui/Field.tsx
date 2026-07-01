"use client";

import { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

// Label + control wrapper. Every form field uses this so labels are always
// persistent (never placeholder-only). See docs/design-system.md §9.
export function Field({
  label,
  htmlFor,
  required,
  helper,
  error,
  children,
}: {
  label?: string;
  htmlFor?: string;
  required?: boolean;
  helper?: ReactNode;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={htmlFor} className="block text-sm font-medium" style={{ color: "var(--text-muted)" }}>
          {label}
          {required && <span style={{ color: "var(--coral)" }}> *</span>}
        </label>
      )}
      {children}
      {error ? (
        <p className="text-xs" style={{ color: "var(--coral)" }}>{error}</p>
      ) : helper ? (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>{helper}</p>
      ) : null}
    </div>
  );
}

const controlBase =
  "w-full px-4 py-3 rounded-md text-[15px] transition placeholder:text-slate-400";
const controlStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  color: "var(--text)",
};

export function Input({ className = "", style, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${controlBase} ${className}`} style={{ ...controlStyle, ...style }} />;
}

export function Textarea({ className = "", style, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`${controlBase} resize-y leading-relaxed ${className}`}
      style={{ ...controlStyle, ...style }}
    />
  );
}
