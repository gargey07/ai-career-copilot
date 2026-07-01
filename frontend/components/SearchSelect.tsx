"use client";

import { useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import { useDebouncedValue } from "@/lib/useDebouncedValue";

interface SearchSelectProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  /** Backend-suggestion field — fetches from /api/suggestions/{apiField}?q= */
  apiField?: "roles" | "tools" | "skills";
  /** Local static list to filter instead of calling the API (e.g. locations) */
  staticOptions?: string[];
  placeholder?: string;
  helperText?: string;
}

// Reusable type-ahead multi-select: shows removable chips for selected
// values, suggests matches as you type (from the backend taxonomy or a
// local list), and always lets you add a value that isn't suggested.
export default function SearchSelect({
  label,
  values,
  onChange,
  apiField,
  staticOptions,
  placeholder,
  helperText,
}: SearchSelectProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debouncedQuery = useDebouncedValue(query, 250);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Local static-list filtering (locations, etc.)
  useEffect(() => {
    if (!staticOptions) return;
    const q = debouncedQuery.trim().toLowerCase();
    const list = q
      ? [
          ...staticOptions.filter((s) => s.toLowerCase().startsWith(q)),
          ...staticOptions.filter((s) => s.toLowerCase().includes(q) && !s.toLowerCase().startsWith(q)),
        ]
      : staticOptions;
    setSuggestions(list.slice(0, 20));
  }, [debouncedQuery, staticOptions]);

  // Backend taxonomy fetching (roles/tools/skills)
  useEffect(() => {
    if (!apiField) return;
    let cancelled = false;
    fetch(`${API_URL}/api/suggestions/${apiField}?q=${encodeURIComponent(debouncedQuery)}`)
      .then((r) => (r.ok ? r.json() : { results: [] }))
      .then((data) => {
        if (!cancelled) setSuggestions(data.results || []);
      })
      .catch(() => {
        if (!cancelled) setSuggestions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, apiField]);

  const addValue = (val: string) => {
    const trimmed = val.trim();
    if (!trimmed) return;
    if (!values.some((v) => v.toLowerCase() === trimmed.toLowerCase())) {
      onChange([...values, trimmed]);
    }
    setQuery("");
    setOpen(false);
  };

  const removeValue = (val: string) => onChange(values.filter((v) => v !== val));

  const visibleSuggestions = suggestions.filter(
    (s) => !values.some((v) => v.toLowerCase() === s.toLowerCase())
  );
  const exactMatch = visibleSuggestions.some((s) => s.toLowerCase() === query.trim().toLowerCase());

  return (
    <div ref={containerRef} className="relative">
      <label className="block text-sm text-gray-400 mb-2">{label}</label>

      {values.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {values.map((val) => (
            <span
              key={val}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-blue-600/30 border border-blue-500 text-blue-300"
            >
              {val}
              <button
                type="button"
                onClick={() => removeValue(val)}
                className="text-blue-300 hover:text-white transition-colors leading-none"
                aria-label={`Remove ${val}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <input
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            addValue(query);
          }
        }}
        placeholder={placeholder || `Search ${label.toLowerCase()}…`}
        className="w-full px-4 py-3 rounded-xl text-white placeholder-gray-600 transition"
        style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
      />

      {helperText && <p className="text-xs text-gray-600 mt-1.5">{helperText}</p>}

      {open && (query.length > 0 || visibleSuggestions.length > 0) && (
        <div
          className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded-xl shadow-xl"
          style={{ background: "#0f0f24", border: "1px solid rgba(255,255,255,0.1)" }}
        >
          {visibleSuggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => addValue(s)}
              className="w-full text-left px-4 py-2.5 text-sm text-gray-200 hover:bg-white/5 transition-colors"
            >
              {s}
            </button>
          ))}
          {query.trim() && !exactMatch && (
            <button
              type="button"
              onClick={() => addValue(query)}
              className="w-full text-left px-4 py-2.5 text-sm border-t border-white/5"
              style={{ color: "#60a5fa" }}
            >
              + Add &quot;{query.trim()}&quot;
            </button>
          )}
          {visibleSuggestions.length === 0 && !query.trim() && (
            <div className="px-4 py-2.5 text-sm text-gray-600">Type to search…</div>
          )}
        </div>
      )}
    </div>
  );
}
