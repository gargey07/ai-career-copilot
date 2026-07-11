"use client";

import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { Skeleton } from "@/components/ui/Skeleton";

interface SearchInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  apiField: "roles" | "tools" | "skills" | "locations";
  placeholder?: string;
  helperText?: string;
}

// Single-value type-ahead: a text field that shows live suggestions from the
// backend taxonomy. Same fetch behavior as SearchSelect (150ms debounce,
// skeleton, out-of-order guard) but stores one string instead of chips.
export default function SearchInput({ label, value, onChange, apiField, placeholder, helperText }: SearchInputProps) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const requestSeq = useRef(0);
  const debouncedValue = useDebouncedValue(value, 150);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!open) return;
    const seq = ++requestSeq.current;
    setLoading(true);
    fetch(`${API_URL}/api/suggestions/${apiField}?q=${encodeURIComponent(debouncedValue)}`)
      .then((r) => (r.ok ? r.json() : { results: [] }))
      .then((data) => {
        if (seq === requestSeq.current) {
          setSuggestions(data.results || []);
          setLoading(false);
        }
      })
      .catch(() => {
        if (seq === requestSeq.current) {
          setSuggestions([]);
          setLoading(false);
        }
      });
  }, [debouncedValue, apiField, open]);

  const visible = suggestions.filter((s) => s.toLowerCase() !== value.trim().toLowerCase());

  return (
    <div ref={containerRef} className="relative space-y-1.5">
      <label className="block text-sm font-medium" style={{ color: "var(--text-muted)" }}>{label}</label>
      <div className="relative">
        <Search size={18} strokeWidth={1.75} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--text-muted)" }} />
        <input
          type="text"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder || `Search ${label.toLowerCase()}…`}
          className="w-full pl-10 pr-4 py-3 rounded-md text-[15px] transition placeholder:text-slate-400"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
        />
      </div>
      {helperText && <p className="text-xs" style={{ color: "var(--text-muted)" }}>{helperText}</p>}

      {open && (loading || visible.length > 0) && (
        <div
          className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded-md"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-e2)" }}
        >
          {loading && visible.length === 0 ? (
            <div className="p-2 space-y-2">
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-6 w-1/2" />
            </div>
          ) : (
            visible.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  onChange(s);
                  setOpen(false);
                }}
                className="w-full text-left px-4 py-2.5 text-sm transition hover:bg-[var(--surface-muted)]"
                style={{ color: "var(--text)" }}
              >
                {s}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
