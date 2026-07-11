"use client";

import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { Chip } from "@/components/ui/Chip";
import { Skeleton } from "@/components/ui/Skeleton";

interface SearchSelectProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  /** Backend-suggestion field — fetches from /api/suggestions/{apiField}?q= */
  apiField?: "roles" | "tools" | "skills" | "locations";
  /** Local static list to filter instead of calling the API */
  staticOptions?: string[];
  placeholder?: string;
  helperText?: string;
  /**
   * Validates a CUSTOM (typed) entry before it becomes a chip — return an
   * error message to reject, null to accept. Entries picked from the
   * suggestion list skip this (the list is pre-vetted). Used by the
   * locations field so unresolvable places get a hint instead of silently
   * degrading job fetching later.
   */
  validateAdd?: (value: string) => Promise<string | null>;
}

// Reusable type-ahead multi-select: chips for selected values, live
// suggestions (backend taxonomy or a local list), always-available "add
// custom". See docs/design-system.md §9.
export default function SearchSelect({
  label,
  values,
  onChange,
  apiField,
  staticOptions,
  placeholder,
  helperText,
  validateAdd,
}: SearchSelectProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const requestSeq = useRef(0); // guards against out-of-order responses
  const debouncedQuery = useDebouncedValue(query, 150);

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

  // Backend taxonomy fetching (roles/tools/skills). Keeps previous results
  // visible while a new request is in flight, and ignores stale responses.
  useEffect(() => {
    if (!apiField) return;
    const seq = ++requestSeq.current;
    setLoading(true);
    fetch(`${API_URL}/api/suggestions/${apiField}?q=${encodeURIComponent(debouncedQuery)}`)
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
  }, [debouncedQuery, apiField]);

  const addValue = async (val: string, vetted = false) => {
    const trimmed = val.trim();
    if (!trimmed) return;
    // Custom (typed) entries get validated; suggestion picks are vetted.
    // Typing something that exactly matches a suggestion counts as vetted.
    const matchesSuggestion = suggestions.some((s) => s.toLowerCase() === trimmed.toLowerCase());
    if (!vetted && !matchesSuggestion && validateAdd) {
      setValidating(true);
      let error: string | null = null;
      try {
        error = await validateAdd(trimmed);
      } catch {
        error = null; // fail open — validation must never block signup on a network blip
      }
      setValidating(false);
      if (error) {
        setAddError(error);
        return; // keep the query so the user can fix it
      }
    }
    setAddError(null);
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
    <div ref={containerRef} className="relative space-y-1.5">
      <label className="block text-sm font-medium" style={{ color: "var(--text-muted)" }}>
        {label}
      </label>

      {values.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {values.map((val) => (
            <Chip key={val} label={val} onRemove={() => removeValue(val)} />
          ))}
        </div>
      )}

      <div className="relative">
        <Search
          size={18}
          strokeWidth={1.75}
          className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none"
          style={{ color: "var(--text-muted)" }}
        />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            if (addError) setAddError(null);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addValue(query);
            }
          }}
          placeholder={placeholder || `Search ${label.toLowerCase()}…`}
          className="w-full pl-10 pr-4 py-3 rounded-md text-[15px] transition placeholder:text-slate-400"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
        />
      </div>

      {helperText && <p className="text-xs" style={{ color: "var(--text-muted)" }}>{helperText}</p>}
      {addError && <p className="text-xs" style={{ color: "var(--coral)" }}>{addError}</p>}

      {open && (query.length > 0 || visibleSuggestions.length > 0 || loading) && (
        <div
          className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded-md"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-e2)" }}
        >
          {loading && visibleSuggestions.length === 0 ? (
            <div className="p-2 space-y-2">
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-6 w-2/3" />
              <Skeleton className="h-6 w-1/2" />
            </div>
          ) : (
            <>
              {visibleSuggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => addValue(s, true)}
                  className="w-full text-left px-4 py-2.5 text-sm transition hover:bg-[var(--surface-muted)]"
                  style={{ color: "var(--text)" }}
                >
                  {s}
                </button>
              ))}
              {query.trim() && !exactMatch && (
                <button
                  type="button"
                  onClick={() => addValue(query)}
                  disabled={validating}
                  className="w-full text-left px-4 py-2.5 text-sm font-medium border-t transition hover:bg-[var(--surface-muted)] disabled:opacity-60"
                  style={{ color: "var(--primary)", borderColor: "var(--border)" }}
                >
                  {validating ? "Checking…" : <>+ Add &quot;{query.trim()}&quot;</>}
                </button>
              )}
              {!query.trim() && visibleSuggestions.length === 0 && (
                <div className="px-4 py-2.5 text-sm" style={{ color: "var(--text-muted)" }}>
                  Type to search…
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
