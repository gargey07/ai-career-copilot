"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Sun,
  Briefcase,
  Target,
  FileText,
  Sparkles,
  Download,
  ExternalLink,
  AlertTriangle,
  Clock,
  ThumbsUp,
  ThumbsDown,
  RefreshCw,
  Mail,
  MapPin,
  type LucideIcon,
} from "lucide-react";
import { API_URL } from "@/lib/api";
import { getStoredProfile, saveStoredProfile } from "@/lib/localProfile";
import { BrandMark } from "@/components/BrandMark";
import { AiDisclosure } from "@/components/AiDisclosure";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";

// ── Types ──────────────────────────────────────────────────────────────────────
interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  is_remote: boolean;
  source_url: string;
  salary_min?: number | null;
  salary_max?: number | null;
  currency?: string | null;
}

// Components the matcher actually computed for this row — never decorative
// (backend/core/matcher.py _build_breakdown).
interface MatchBreakdown {
  source?: string;
  matched_terms?: string[];
  title_terms?: string[];
  similarity?: number;
}
// AI recruiter evaluation — the one stage that reads the job description
// against the resume with comprehension (backend/core/recruiter.py). Verdict
// is qualitative on purpose: no invented "interview probability" numbers.
interface RecruiterEval {
  verdict?: string; // apply | stretch | skip
  fit_score?: number | null;
  strengths?: string[];
  missing?: string[];
  risks?: string[];
  reason?: string;
}
interface UserJob {
  id: string;
  match_score: number;
  pdf_url: string | null;
  digest_date: string;
  status: string;
  applied_at?: string | null;
  jobs: Job;
  feedback?: string | null;
  feedback_reason?: string | null;
  job_feedback?: string | null;
  // Whether a resume was ever queued for this match at all — distinguishes
  // "not selected for AI tailoring" (normal — only top matches get one)
  // from "generation failed" (TICKET-020). See backend/api/routes/users.py.
  has_optimized_resume?: boolean;
  has_cover_letter?: boolean;
  // User-asserted application progress (applied/interviewing/offer/rejected).
  application_status?: string | null;
  match_breakdown?: MatchBreakdown | null;
  recruiter_eval?: RecruiterEval | null;
}

// Salary display — only ever real source-API numbers; most boards don't
// publish one, and we say so instead of inventing a range.
function formatSalary(job: Job): string | null {
  const symbol = job.currency === "INR" ? "₹" : job.currency === "USD" ? "$" : job.currency === "GBP" ? "£" : job.currency === "EUR" ? "€" : job.currency ? `${job.currency} ` : "";
  const fmt = (n: number) => (n >= 100000 ? `${Math.round(n / 1000)}k` : `${n}`);
  if (job.salary_min && job.salary_max) return `${symbol}${fmt(job.salary_min)}–${symbol}${fmt(job.salary_max)}`;
  if (job.salary_min) return `From ${symbol}${fmt(job.salary_min)}`;
  if (job.salary_max) return `Up to ${symbol}${fmt(job.salary_max)}`;
  return null;
}

// The signed dashboard token IS the user's key — backend endpoints reject
// bare user_ids (backend/core/access_token.py). Format: "{user_id}.{sig}".
function userIdFromToken(token: string): string | null {
  const i = token.lastIndexOf(".");
  return i > 0 ? token.slice(0, i) : null;
}

// Job-relevance reasons — "this JOB isn't for me" (feeds matching
// penalties), distinct from the resume-quality chips below.
const JOB_FEEDBACK_REASONS: { value: string; label: string }[] = [
  { value: "wrong_role", label: "Wrong kind of role" },
  { value: "too_senior", label: "Too senior" },
  { value: "too_junior", label: "Too junior" },
  { value: "wrong_location", label: "Wrong location" },
  { value: "company", label: "Not this company" },
];
interface User {
  id: string;
  name: string;
  email: string;
  target_roles: string[];
  profile_strength?: number;
  preferred_digest_time?: string | null;
}

// TICKET-008: optional reason chips on a thumbs-down — never required,
// never blocks the click.
const FEEDBACK_REASONS: { value: string; label: string }[] = [
  { value: "too_generic", label: "Too generic" },
  { value: "missing_skills", label: "Missing skills" },
  { value: "wrong_project_highlighted", label: "Wrong project highlighted" },
  { value: "experience_not_prioritized", label: "Experience not prioritized" },
  { value: "formatting_issue", label: "Formatting issue" },
  { value: "other", label: "Other" },
];

// Stored match scores exist in two scales: 0–1 (original matcher) and 0–100
// (the replaced match_jobs SQL function returns percentages directly). Treat
// anything > 1 as already-a-percentage — without this, 79.3 renders as 7930%.
export function normalizeScorePct(score: number): number {
  const pct = score <= 1 ? score * 100 : score;
  return Math.min(100, Math.max(0, Math.round(pct)));
}

// ── Score badge (CSS dot, no emoji) ─────────────────────────────────────────────
function ScoreBadge({ score }: { score: number }) {
  const pct = normalizeScorePct(score);
  const cls = pct >= 85 ? "badge-green" : pct >= 70 ? "badge-yellow" : "badge-orange";
  const dot = pct >= 85 ? "#0F9D8C" : pct >= 70 ? "#F59E0B" : "#F97316";
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${cls}`}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: dot }} />
      {pct}% Match
    </span>
  );
}

// ── Stat card ────────────────────────────────────────────────────────────────────
function StatCard({
  icon: Icon,
  label,
  value,
  onClick,
  active,
  hint,
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  onClick?: () => void;
  active?: boolean;
  hint?: string;
}) {
  const body = (
    <Card
      className={`p-5 h-full ${onClick ? "transition-shadow hover:shadow-md" : ""}`}
      style={active ? { borderColor: "var(--primary)", boxShadow: "0 0 0 1px var(--primary)" } : undefined}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>{label}</span>
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-2xl font-extrabold" style={{ color: "var(--text)" }}>{value}</div>
        {onClick && (
          <span className="text-xs font-medium" style={{ color: "var(--primary)" }}>
            {active ? "Clear" : hint || "View"}
          </span>
        )}
      </div>
    </Card>
  );
  if (!onClick) return body;
  return (
    <button type="button" onClick={onClick} className="text-left w-full cursor-pointer" aria-pressed={active}>
      {body}
    </button>
  );
}

// ── Resume feedback widget (thumbs up/down + reason chips) ─────────────────────
function ResumeFeedback({ userId, token, match }: { userId: string; token: string; match: UserJob }) {
  const [feedback, setFeedback] = useState<string | null>(match.feedback || null);
  const [pickingReason, setPickingReason] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (value: "up" | "down", reason = "") => {
    setSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/matches/${match.id}/feedback?t=${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: value, reason }),
      });
      if (res.ok) {
        setFeedback(value);
        setPickingReason(false);
      }
    } catch {
      // best-effort — leave the buttons active so they can retry
    } finally {
      setSubmitting(false);
    }
  };

  if (feedback) {
    return (
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
        Thanks for the feedback{feedback === "down" ? " — we'll use it to improve" : ""}.
      </p>
    );
  }

  if (pickingReason) {
    return (
      <div className="space-y-2">
        <p className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>What was off?</p>
        <div className="flex flex-wrap gap-2">
          {FEEDBACK_REASONS.map((r) => (
            <button
              key={r.value}
              type="button"
              disabled={submitting}
              onClick={() => submit("down", r.value)}
              className="px-2.5 py-1 rounded-full text-xs border transition hover:border-[var(--primary)] hover:text-[var(--text)]"
              style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
            >
              {r.label}
            </button>
          ))}
          <button
            type="button"
            disabled={submitting}
            onClick={() => submit("down")}
            className="px-2.5 py-1 text-xs hover:underline"
            style={{ color: "var(--text-muted)" }}
          >
            Skip
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>Was this resume useful?</span>
      <button
        type="button"
        disabled={submitting}
        onClick={() => submit("up")}
        aria-label="This resume was good"
        className="p-1.5 rounded-md transition hover:bg-[var(--surface-muted)]"
      >
        <ThumbsUp size={15} strokeWidth={1.75} style={{ color: "var(--text-muted)" }} />
      </button>
      <button
        type="button"
        disabled={submitting}
        onClick={() => setPickingReason(true)}
        aria-label="This resume needs improvement"
        className="p-1.5 rounded-md transition hover:bg-[var(--surface-muted)]"
      >
        <ThumbsDown size={15} strokeWidth={1.75} style={{ color: "var(--text-muted)" }} />
      </button>
    </div>
  );
}

// PDF generation runs in the background — after kicking one off, the page
// refetches itself once the render has had time to finish, instead of
// telling the user to refresh manually and leaving a stuck-looking label.
const REFRESH_EVENT = "acc:refresh-dashboard";
const PDF_REFRESH_DELAY_MS = 50_000;

function useDelayedDashboardRefresh(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const timer = setTimeout(() => window.dispatchEvent(new Event(REFRESH_EVENT)), PDF_REFRESH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [active]);
}

// ── Retry button for a failed/stuck PDF (TICKET-020) ────────────────────────────
// Never leave a permanent "Resume generating…" with no way out.
function RetryPdfButton({ userId, token, matchId }: { userId: string; token: string; matchId: string }) {
  const [state, setState] = useState<"idle" | "retrying" | "started">("idle");
  useDelayedDashboardRefresh(state === "started");

  const retry = async () => {
    setState("retrying");
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/matches/${matchId}/retry-pdf?t=${encodeURIComponent(token)}`, { method: "POST" });
      setState(res.ok ? "started" : "idle");
    } catch {
      setState("idle");
    }
  };

  if (state === "started") {
    return (
      <span className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm" style={{ background: "var(--surface-muted)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
        <Clock size={16} strokeWidth={1.75} />
        Retrying — this page refreshes itself in about a minute
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={retry}
      disabled={state === "retrying"}
      className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-semibold transition hover:bg-[var(--surface-muted)] disabled:opacity-60"
      style={{ border: "1px solid var(--coral)", color: "var(--coral)" }}
    >
      <RefreshCw size={16} strokeWidth={1.75} className={state === "retrying" ? "animate-spin" : ""} />
      {state === "retrying" ? "Retrying…" : "Resume failed — Retry"}
    </button>
  );
}

// ── "I applied" toggle — user-asserted, the honest Applications metric ─────────
function AppliedButton({ userId, token, match }: { userId: string; token: string; match: UserJob }) {
  const [applied, setApplied] = useState(match.status === "applied");
  const [saving, setSaving] = useState(false);

  const toggle = async () => {
    const next = !applied;
    setSaving(true);
    setApplied(next); // optimistic
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/matches/${match.id}/applied?t=${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ applied: next }),
      });
      if (!res.ok) setApplied(!next); // roll back
    } catch {
      setApplied(!next);
    } finally {
      setSaving(false);
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={saving}
      aria-pressed={applied}
      className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-semibold transition disabled:opacity-60"
      style={
        applied
          ? { background: "#ECFDF5", border: "1px solid #A7F3D0", color: "#0F9D8C" }
          : { border: "1px solid var(--border)", color: "var(--text-muted)" }
      }
      title={applied ? "Tap to undo" : "Mark that you applied to this job"}
    >
      {applied ? "Applied ✓" : "I applied"}
    </button>
  );
}

// ── On-demand "Generate Tailored Resume" — for matches the pipeline's
// top-N auto-generation didn't cover. Quota-gated server-side.
function GenerateResumeButton({ userId, token, matchId }: { userId: string; token: string; matchId: string }) {
  const [state, setState] = useState<"idle" | "requesting" | "started" | "capped">("idle");
  useDelayedDashboardRefresh(state === "started");

  const generate = async () => {
    setState("requesting");
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/matches/${matchId}/generate-resume?t=${encodeURIComponent(token)}`, { method: "POST" });
      if (res.status === 429) setState("capped");
      else setState(res.ok ? "started" : "idle");
    } catch {
      setState("idle");
    }
  };

  if (state === "capped") {
    return (
      <span className="inline-flex items-center px-4 py-2.5 rounded-md text-sm" style={{ background: "var(--surface-muted)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
        Daily resume allowance used — more tomorrow
      </span>
    );
  }
  if (state === "started") {
    return (
      <span className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm" style={{ background: "var(--surface-muted)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
        <Clock size={16} strokeWidth={1.75} />
        Generating — this page refreshes itself in about a minute
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={generate}
      disabled={state === "requesting"}
      className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-semibold transition hover:bg-[var(--surface-muted)] disabled:opacity-60"
      style={{ border: "1px solid var(--primary)", color: "var(--primary)" }}
    >
      <FileText size={16} strokeWidth={1.75} />
      {state === "requesting" ? "Starting…" : "Generate Tailored Resume"}
    </button>
  );
}

// ── On-demand cover letter — never automatic, shown in a copyable modal ────────
function CoverLetterButton({ userId, token, match }: { userId: string; token: string; match: UserJob }) {
  const [open, setOpen] = useState(false);
  const [letter, setLetter] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "capped" | "error">("idle");
  const [copied, setCopied] = useState(false);

  const fetchLetter = async (regenerate: boolean) => {
    setState("loading");
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/matches/${match.id}/generate-cover-letter?t=${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ regenerate }),
      });
      if (res.status === 429) {
        setState("capped");
        return;
      }
      if (!res.ok) {
        setState("error");
        return;
      }
      const data = await res.json();
      setLetter(data.cover_letter);
      setState("idle");
    } catch {
      setState("error");
    }
  };

  const openModal = () => {
    setOpen(true);
    if (!letter) fetchLetter(false);
  };

  const copy = async () => {
    if (!letter) return;
    try {
      await navigator.clipboard.writeText(letter);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard unavailable — user can select manually */ }
  };

  return (
    <>
      <button
        type="button"
        onClick={openModal}
        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-semibold transition hover:bg-[var(--surface-muted)]"
        style={{ border: "1px solid var(--border)", color: "var(--text)" }}
      >
        <Mail size={16} strokeWidth={1.75} />
        {match.has_cover_letter ? "View Cover Letter" : "Cover Letter"}
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(15,47,58,0.45)" }}
          onClick={() => setOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Cover letter"
        >
          <div
            className="w-full max-w-xl rounded-lg p-6 max-h-[85vh] flex flex-col"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold" style={{ color: "var(--text)" }}>
                Cover letter — {match.jobs.title} at {match.jobs.company}
              </h3>
              <button type="button" onClick={() => setOpen(false)} className="text-sm hover:underline" style={{ color: "var(--text-muted)" }}>
                Close
              </button>
            </div>
            {state === "loading" ? (
              <p className="text-sm py-8 text-center" style={{ color: "var(--text-muted)" }}>Writing your cover letter — usually 5–15 seconds…</p>
            ) : state === "capped" ? (
              <p className="text-sm py-8 text-center" style={{ color: "var(--text-muted)" }}>You&apos;ve used today&apos;s cover-letter allowance — more unlock tomorrow.</p>
            ) : state === "error" ? (
              <p className="text-sm py-8 text-center" style={{ color: "var(--coral)" }}>Couldn&apos;t generate the letter right now — close this and try again in a minute.</p>
            ) : letter ? (
              <>
                <textarea
                  readOnly
                  value={letter}
                  className="w-full flex-1 min-h-[260px] rounded-md p-3 text-sm leading-relaxed outline-none resize-y"
                  style={{ border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)" }}
                />
                <div className="flex items-center justify-between mt-3">
                  <button
                    type="button"
                    onClick={() => fetchLetter(true)}
                    className="text-xs hover:underline"
                    style={{ color: "var(--text-muted)" }}
                    title="Uses one of today's cover-letter generations"
                  >
                    Regenerate
                  </button>
                  <button
                    type="button"
                    onClick={copy}
                    className="px-4 py-2 rounded-md text-sm font-semibold text-white transition hover:opacity-90"
                    style={{ background: "var(--primary)" }}
                  >
                    {copied ? "Copied" : "Copy to clipboard"}
                  </button>
                </div>
                <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                  AI-drafted from your real resume — read it over and make it yours before sending.
                </p>
              </>
            ) : null}
          </div>
        </div>
      )}
    </>
  );
}

// ── Application progress — user-asserted, appears once "I applied" is on ───────
const APPLICATION_STATUSES: { value: string; label: string }[] = [
  { value: "applied", label: "Applied" },
  { value: "interviewing", label: "Interviewing" },
  { value: "offer", label: "Got an offer" },
  { value: "rejected", label: "Rejected" },
];

function ApplicationStatusSelect({ userId, token, match }: { userId: string; token: string; match: UserJob }) {
  const [status, setStatus] = useState(match.application_status || "applied");
  const [saving, setSaving] = useState(false);

  const save = async (next: string) => {
    const prev = status;
    setStatus(next);
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/matches/${match.id}/application-status?t=${encodeURIComponent(token)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next }),
      });
      if (!res.ok) setStatus(prev);
    } catch {
      setStatus(prev);
    } finally {
      setSaving(false);
    }
  };

  return (
    <label className="inline-flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
      Status
      <select
        value={status}
        disabled={saving}
        onChange={(e) => save(e.target.value)}
        className="px-2 py-1.5 rounded-md text-xs outline-none disabled:opacity-60"
        style={{ border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)" }}
        aria-label="Application status"
      >
        {APPLICATION_STATUSES.map((s) => (
          <option key={s.value} value={s.value}>{s.label}</option>
        ))}
      </select>
    </label>
  );
}

// ── "Not relevant" — job-fit feedback that feeds matching penalties ────────────
function NotRelevant({ userId, token, match }: { userId: string; token: string; match: UserJob }) {
  const [state, setState] = useState<"idle" | "picking" | "done">(
    match.job_feedback === "not_relevant" ? "done" : "idle"
  );
  const [submitting, setSubmitting] = useState(false);

  const submit = async (reason: string) => {
    setSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/matches/${match.id}/job-feedback?t=${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      });
      if (res.ok) setState("done");
    } catch {
      // stay in picking state so they can retry
    } finally {
      setSubmitting(false);
    }
  };

  if (state === "done") {
    return (
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
        Noted — we&apos;ll avoid jobs like this for you.
      </p>
    );
  }

  if (state === "picking") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Why not?</span>
        {JOB_FEEDBACK_REASONS.map((r) => (
          <button
            key={r.value}
            type="button"
            disabled={submitting}
            onClick={() => submit(r.value)}
            className="px-2.5 py-1 rounded-full text-xs border transition hover:border-[var(--primary)] hover:text-[var(--text)]"
            style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
          >
            {r.label}
          </button>
        ))}
        <button
          type="button"
          disabled={submitting}
          onClick={() => submit("")}
          className="px-2.5 py-1 text-xs hover:underline"
          style={{ color: "var(--text-muted)" }}
        >
          Skip
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setState("picking")}
      className="text-xs hover:underline"
      style={{ color: "var(--text-muted)" }}
    >
      Not relevant?
    </button>
  );
}

// ── "Why this matched" — real computed components only ─────────────────────────
function WhyThisMatched({ breakdown }: { breakdown: MatchBreakdown }) {
  const [open, setOpen] = useState(false);
  const terms = breakdown.matched_terms || [];
  const titleTerms = new Set(breakdown.title_terms || []);
  if (!terms.length && breakdown.similarity == null) return null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs hover:underline"
        style={{ color: "var(--text-muted)" }}
        aria-expanded={open}
      >
        {open ? "Hide" : "Why this matched"}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {terms.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>From your profile:</span>
              {terms.map((t) => (
                <span
                  key={t}
                  className="px-2 py-0.5 rounded-full text-xs"
                  style={
                    titleTerms.has(t)
                      ? { background: "#FEF3C7", color: "#B45309", border: "1px solid #FDE68A" }
                      : { background: "var(--surface-muted)", color: "var(--text-muted)", border: "1px solid var(--border)" }
                  }
                  title={titleTerms.has(t) ? "Also appears in the job title" : "Appears in the job description"}
                >
                  {t}
                </span>
              ))}
            </div>
          )}
          {breakdown.source === "vector" && (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Ranked by overall similarity between your resume and this posting
              {breakdown.similarity != null && ` (${Math.round(breakdown.similarity * 100)}%)`}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── AI recruiter's take — verdict + written reasoning + gap analysis ──────────
// Qualitative only (Apply / Stretch / Not recommended): never a fabricated
// "interview probability" percentage (docs/PRODUCT_STRATEGY_BETA.md, Trust).
const VERDICT_STYLES: Record<string, { label: string; bg: string; color: string; border: string }> = {
  apply: { label: "Recruiter's take: Apply", bg: "#DCFCE7", color: "#15803D", border: "#BBF7D0" },
  stretch: { label: "Recruiter's take: Worth a shot", bg: "#FEF3C7", color: "#B45309", border: "#FDE68A" },
  skip: { label: "Recruiter's take: Not recommended", bg: "#FEE2E2", color: "#B91C1C", border: "#FECACA" },
};

function RecruiterInsight({ evaluation }: { evaluation: RecruiterEval }) {
  const style = VERDICT_STYLES[(evaluation.verdict || "").toLowerCase()];
  if (!style) return null;
  const strengths = evaluation.strengths || [];
  // Missing skills and risks answer the same user question ("what's the
  // gap?") — one list keeps the card compact.
  const gaps = [...(evaluation.missing || []), ...(evaluation.risks || [])];
  return (
    <div className="space-y-2 rounded-md p-3" style={{ background: "var(--surface-muted)", border: "1px solid var(--border)" }}>
      <span
        className="inline-block px-2 py-0.5 rounded-full text-xs font-semibold"
        style={{ background: style.bg, color: style.color, border: `1px solid ${style.border}` }}
      >
        {style.label}
      </span>
      {evaluation.reason && (
        <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
          {evaluation.reason}
        </p>
      )}
      {strengths.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {strengths.map((s, i) => (
            <span key={`s-${i}`} className="px-2 py-0.5 rounded-full text-xs" style={{ background: "#DCFCE7", color: "#15803D", border: "1px solid #BBF7D0" }}>
              ✓ {s}
            </span>
          ))}
        </div>
      )}
      {gaps.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {gaps.map((s, i) => (
            <span key={`g-${i}`} className="px-2 py-0.5 rounded-full text-xs" style={{ background: "var(--surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
              ✗ {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Job card ─────────────────────────────────────────────────────────────────────
function JobCard({ match, index, userId, token }: { match: UserJob; index: number; userId: string; token: string }) {
  const job = match.jobs;
  const hasApply = job.source_url && !job.source_url.includes("example.com");
  const salary = formatSalary(job);

  // A resume was queued (has_optimized_resume) but never got a pdf_url:
  // either it's still in the narrow "generating" window (status still
  // 'resume_ready'), or it's stuck/failed (status moved on — e.g.
  // 'pdf_failed', or even 'emailed' if the digest went out before a stuck
  // legacy row got fixed). Treat anything past 'resume_ready' as
  // retry-eligible rather than enumerating every failure status.
  const pdfNeverResolved = !!match.has_optimized_resume && !match.pdf_url;
  const pdfInProgress = pdfNeverResolved && match.status === "resume_ready";
  const pdfStuckOrFailed = pdfNeverResolved && !pdfInProgress;

  return (
    <Card className="p-6 space-y-4 animate-fade-in transition hover:shadow-e2" style={{ animationDelay: `${index * 60}ms` }}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-lg font-bold" style={{ color: "var(--text)" }}>{job.title}</h3>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
            {job.company}
            {job.location && ` · ${job.location}`}
            {job.is_remote && (
              <span className="ml-2 px-2 py-0.5 rounded-full text-xs" style={{ background: "#FEF3C7", color: "#B45309", border: "1px solid #FDE68A" }}>
                Remote
              </span>
            )}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            {salary ?? "Salary not disclosed"}
          </p>
        </div>
        <ScoreBadge score={match.match_score} />
      </div>

      {match.recruiter_eval && <RecruiterInsight evaluation={match.recruiter_eval} />}

      <div className="flex flex-wrap gap-3">
        {match.pdf_url ? (
          <a
            href={match.pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-semibold text-white transition hover:opacity-90"
            style={{ background: "var(--primary)" }}
          >
            <Download size={16} strokeWidth={1.75} />
            View Tailored Resume
          </a>
        ) : pdfStuckOrFailed ? (
          <RetryPdfButton userId={userId} token={token} matchId={match.id} />
        ) : pdfInProgress ? (
          <span className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm" style={{ background: "var(--surface-muted)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
            <Clock size={16} strokeWidth={1.75} />
            Resume generating…
          </span>
        ) : (
          <GenerateResumeButton userId={userId} token={token} matchId={match.id} />
        )}

        <CoverLetterButton userId={userId} token={token} match={match} />

        {hasApply ? (
          <a
            href={`${API_URL}/r/${match.id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-semibold transition hover:bg-[var(--surface-muted)]"
            style={{ border: "1px solid var(--border)", color: "var(--text)" }}
          >
            <ExternalLink size={16} strokeWidth={1.75} />
            Apply Now
          </a>
        ) : (
          <span className="inline-flex items-center px-4 py-2.5 rounded-md text-sm" style={{ border: "1px solid var(--border)", color: "var(--text-muted)" }}>
            Apply link coming soon
          </span>
        )}

        <AppliedButton userId={userId} token={token} match={match} />
        {(match.status === "applied" || match.applied_at) && (
          <ApplicationStatusSelect userId={userId} token={token} match={match} />
        )}
      </div>

      <div className="pt-3 flex flex-wrap items-center justify-between gap-3" style={{ borderTop: "1px solid var(--border)" }}>
        {match.pdf_url ? (
          <ResumeFeedback userId={userId} token={token} match={match} />
        ) : <span />}
        <div className="flex flex-wrap items-center gap-4">
          {match.match_breakdown && <WhyThisMatched breakdown={match.match_breakdown} />}
          <NotRelevant userId={userId} token={token} match={match} />
        </div>
      </div>
    </Card>
  );
}

// ── T-012: Digest Time Picker ─────────────────────────────────────────────────
const TIME_SLOTS = [
  { label: "6:00 AM", value: "06:00:00" },
  { label: "7:00 AM", value: "07:00:00" },
  { label: "8:00 AM", value: "08:00:00" },
  { label: "9:00 AM", value: "09:00:00" },
];

function DigestTimePicker({
  userId,
  token,
  currentTime,
}: {
  userId: string;
  token: string;
  currentTime?: string | null;
}) {
  const [selected, setSelected] = useState(currentTime || "07:00:00");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save(time: string) {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/preferences?t=${encodeURIComponent(token)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferred_digest_time: time }),
      });
      if (res.ok) {
        setSelected(time);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <Clock size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
        <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>Daily Digest Time</span>
        {saved && <span className="text-xs text-green-500 animate-fade-in ml-auto">Saved!</span>}
      </div>
      <div className="flex gap-2 flex-wrap mb-2">
        {TIME_SLOTS.map((slot) => (
          <button
            key={slot.value}
            disabled={saving}
            onClick={() => save(slot.value)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all border ${
              selected === slot.value
                ? "bg-[var(--primary)] border-[var(--primary)] text-white"
                : "bg-transparent border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--primary)] hover:text-[var(--text)]"
            }`}
          >
            {slot.label}
          </button>
        ))}
      </div>
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Your digest will arrive around this time each morning (IST)</p>
    </Card>
  );
}

// ── Loading skeleton ─────────────────────────────────────────────────────────────
function DashboardSkeleton({ hint }: { hint?: string }) {
  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-8">
      {hint && (
        <p className="text-sm text-center" style={{ color: "var(--text-muted)" }}>{hint}</p>
      )}
      <div className="space-y-3">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-10 w-72" />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
      </div>
      <div className="space-y-4">
        {[0, 1].map((i) => <Skeleton key={i} className="h-36 w-full" />)}
      </div>
    </div>
  );
}

// Render's free tier is a single instance with no redundancy — it can go
// idle (cold start ~50s) or briefly restart mid-request. A single failed
// fetch there is not "your profile is broken", it's "the server was
// asleep" — retry with backoff before showing a hard error. Only retries
// network-level failures and 5xx (server-side); a 4xx like "profile not
// found" is a real error and fails immediately.
const DASHBOARD_RETRY_DELAYS_MS = [0, 5000, 15000, 30000];

class TokenRejectedError extends Error {}

async function fetchDashboardWithRetry(
  userId: string,
  token: string,
  onAttempt?: (attempt: number, total: number) => void
): Promise<{ user: User; jobs: UserJob[] }> {
  let lastError: Error = new Error("Failed to load dashboard.");

  for (let attempt = 0; attempt < DASHBOARD_RETRY_DELAYS_MS.length; attempt++) {
    if (attempt > 0) {
      onAttempt?.(attempt, DASHBOARD_RETRY_DELAYS_MS.length);
      await new Promise((resolve) => setTimeout(resolve, DASHBOARD_RETRY_DELAYS_MS[attempt]));
    }
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/dashboard?t=${encodeURIComponent(token)}`);
      if (res.ok) {
        const data = await res.json();
        return { user: data.user, jobs: (data.jobs as any) || [] };
      }
      const body = await res.json().catch(() => ({}));
      if (res.status === 401) throw new TokenRejectedError(body.detail || "This link is invalid or has expired.");
      lastError = new Error(body.detail || "Failed to load dashboard.");
      if (res.status < 500) break; // real error (e.g. 404) — retrying won't help
    } catch (e: any) {
      if (e instanceof TokenRejectedError) throw e;
      // fetch() threw — network-level failure (server unreachable/restarting)
      lastError = new Error(e.message || "Failed to load dashboard.");
    }
  }
  throw lastError;
}

// ── Invite a friend — measurable sharing, no rewards/claims ─────────────────────
function InviteCard({ userId }: { userId: string }) {
  const [copied, setCopied] = useState(false);
  // Short ref (first UUID segment) — enough to attribute, not enough to
  // identify; the funnel meta is the only place it lands.
  const inviteUrl = typeof window !== "undefined"
    ? `${window.location.origin}/?ref=${userId.split("-")[0]}`
    : "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard unavailable — the visible URL below is selectable
    }
  };

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
        <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>Know someone job hunting?</span>
      </div>
      <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
        The beta is free — share your link and they get the same morning matches you do.
      </p>
      <div className="flex flex-col sm:flex-row gap-2">
        <code
          className="flex-1 px-3 py-2 rounded-md text-xs truncate"
          style={{ background: "var(--surface-muted)", border: "1px solid var(--border)", color: "var(--text-muted)" }}
        >
          {inviteUrl}
        </code>
        <button
          type="button"
          onClick={copy}
          className="px-4 py-2 rounded-md text-sm font-semibold text-white transition hover:opacity-90"
          style={{ background: "var(--primary)" }}
        >
          {copied ? "Copied!" : "Copy link"}
        </button>
      </div>
    </Card>
  );
}

// ── "Email me my dashboard link" — recovery for lost/legacy links ──────────────
function RequestLinkForm() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");

  const submit = async () => {
    if (!email.trim()) return;
    setState("sending");
    try {
      await fetch(`${API_URL}/api/users/request-dashboard-link`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
    } catch {
      // same outcome either way — the message below is deliberately generic
    }
    setState("sent");
  };

  if (state === "sent") {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        If that email has an account, your dashboard link is on its way — check your inbox.
      </p>
    );
  }

  return (
    <div className="flex flex-col sm:flex-row gap-2">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="you@email.com"
        className="flex-1 px-3 py-2.5 rounded-md text-sm outline-none focus:border-[var(--primary)]"
        style={{ border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)" }}
      />
      <button
        type="button"
        onClick={submit}
        disabled={state === "sending" || !email.trim()}
        className="px-4 py-2.5 rounded-md text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
        style={{ background: "var(--primary)" }}
      >
        {state === "sending" ? "Sending…" : "Email me my link"}
      </button>
    </div>
  );
}

// ── Dashboard Content ──────────────────────────────────────────────────────────
function DashboardContent() {
  const params = useSearchParams();
  const paramToken = params.get("t");

  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState("");
  const [allJobs, setAllJobs] = useState<UserJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [errorKind, setErrorKind] = useState<"no-profile" | "load-failed" | "bad-token">("load-failed");
  const [retryHint, setRetryHint] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  // Clicking the "Resumes Ready" stat card filters the whole page down to
  // matches with a finished PDF; clicking again clears it.
  const [showOnlyReady, setShowOnlyReady] = useState(false);
  // One-time view filter by job location — never persisted, never touches
  // the saved preferred_locations. "" = off, "__remote__" = remote jobs,
  // anything else = exact location string from the loaded jobs.
  const [locationFilter, setLocationFilter] = useState("");
  // Today's list is capped by default — pipeline re-runs in a single day
  // can pile up dozens of matches and bury the page.
  const [showAllToday, setShowAllToday] = useState(false);

  const today = new Date().toISOString().split("T")[0];

  // PDF generate/retry buttons fire this after giving the render time to
  // finish — refetching turns "Generating…" into the Download button
  // without the user having to reload manually.
  useEffect(() => {
    const onRefresh = () => setReloadKey((k) => k + 1);
    window.addEventListener(REFRESH_EVENT, onRefresh);
    return () => window.removeEventListener(REFRESH_EVENT, onRefresh);
  }, []);

  useEffect(() => {
    // The signed token comes from the URL (email links) or from what this
    // browser stored at signup/last visit — a bare user_id is no longer
    // enough to load anything (backend/core/access_token.py). Old
    // ?user_id= links land in the "request a fresh link" flow below.
    const activeToken = paramToken || getStoredProfile()?.token || "";
    const userId = activeToken ? userIdFromToken(activeToken) : null;
    if (!activeToken || !userId) {
      const hadLegacyLink = !!params.get("user_id");
      setError(
        hadLegacyLink
          ? "Dashboard links have been upgraded for security — request a fresh one below."
          : "We don't know who you are yet — set up your profile first, or open the dashboard link from your email."
      );
      setErrorKind(hadLegacyLink ? "bad-token" : "no-profile");
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError("");
    setRetryHint("");
    fetchDashboardWithRetry(userId, activeToken, () => {
      if (!cancelled) setRetryHint("Waking up the server — this can take up to a minute on our free tier.");
    })
      .then(({ user, jobs }) => {
        if (cancelled) return;
        setUser(user);
        setToken(activeToken);
        setAllJobs(jobs);
        // Remember the working token so /dashboard works without the URL param next time.
        saveStoredProfile({ id: user.id, name: user.name || "", token: activeToken });
      })
      .catch((e: any) => {
        if (cancelled) return;
        // A real "not found" from the backend vs. the server just being
        // unreachable get different recovery actions below — Render's free
        // tier restarting mid-request is common enough that "set up your
        // profile again" would be actively wrong advice here.
        if (e instanceof TokenRejectedError) {
          setErrorKind("bad-token");
        } else {
          setErrorKind(/couldn.t find a profile/i.test(e.message) ? "no-profile" : "load-failed");
        }
        setError(e.message || "Failed to load dashboard.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [paramToken, today, reloadKey]);

  if (loading) {
    return (
      <main className="min-h-screen" style={{ background: "var(--bg)" }}>
        <DashboardSkeleton hint={retryHint} />
      </main>
    );
  }

  if (error || !user) {
    return (
      <main className="min-h-screen flex items-center justify-center px-6" style={{ background: "var(--bg)" }}>
        <Card className="p-8 text-center max-w-md">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "#FEF2F2" }}>
            <AlertTriangle size={24} strokeWidth={1.75} style={{ color: "var(--coral)" }} />
          </div>
          <h2 className="text-xl font-bold mb-2" style={{ color: "var(--text)" }}>Couldn&apos;t load your dashboard</h2>
          <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>
            {errorKind === "no-profile"
              ? error || "Invalid user ID. Check your link."
              : errorKind === "bad-token"
              ? error || "This link is invalid or has expired."
              : "We couldn't reach the server after a few tries. It may still be waking up — this happens sometimes on our free hosting tier."}
          </p>
          {errorKind === "no-profile" ? (
            <a
              href="/signup"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-semibold text-white transition hover:opacity-90"
              style={{ background: "var(--primary)" }}
            >
              Set up my profile
            </a>
          ) : errorKind === "bad-token" ? (
            <RequestLinkForm />
          ) : (
            <button
              type="button"
              onClick={() => setReloadKey((k) => k + 1)}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-semibold text-white transition hover:opacity-90"
              style={{ background: "var(--primary)" }}
            >
              Try again
            </button>
          )}
        </Card>
      </main>
    );
  }

  const firstName = user.name?.split(" ")[0] || "there";

  // Location filter options come from the jobs actually loaded — no
  // taxonomy call needed, and every option is guaranteed to match something.
  const locationSet = new Set<string>();
  let hasRemote = false;
  for (const j of allJobs) {
    if (j.jobs.is_remote) hasRemote = true;
    const loc = (j.jobs.location || "").trim();
    if (loc && !/^(not specified|remote)$/i.test(loc)) locationSet.add(loc);
  }
  const locationOptions = Array.from(locationSet).sort();
  const matchesLocation = (m: UserJob) =>
    locationFilter === "" ||
    (locationFilter === "__remote__"
      ? m.jobs.is_remote
      : (m.jobs.location || "").trim() === locationFilter);
  // Applying the filter up here means today/ready/history views all
  // respect it (and it composes with the Resumes Ready filter); the
  // applications tracker below deliberately stays unfiltered.
  const visibleJobs = locationFilter ? allJobs.filter(matchesLocation) : allJobs;

  const todayMatches = visibleJobs.filter((j) => j.digest_date === today);
  const jobsFound = todayMatches.length;
  // Ready resumes stay useful across days — count (and filter) all of them,
  // not just today's.
  const readyMatches = visibleJobs
    .filter((m) => m.pdf_url)
    .sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
  const resumesReady = readyMatches.length;
  // Applications the user themselves marked (strategy rule: only ever
  // user-asserted progress) — most recently updated first.
  const applications = allJobs
    .filter((m) => m.applied_at || m.status === "applied" || m.application_status)
    .sort((a, b) => (b.applied_at || "").localeCompare(a.applied_at || ""));
  const bestMatch = todayMatches.length ? Math.max(...todayMatches.map((m) => normalizeScorePct(m.match_score))) : 0;

  // Multiple pipeline runs in one day can pile up dozens of "today"
  // matches — show the top few by default, with an explicit expander.
  const TODAY_DISPLAY_CAP = 10;
  const todayDisplayed = showAllToday ? todayMatches : todayMatches.slice(0, TODAY_DISPLAY_CAP);
  // Last day we actually delivered matches — a real, verifiable metric
  // (strategy rule: never display applications/interviews/offers until we
  // can verify them).
  const lastMatchDate = allJobs.reduce<string | null>(
    (latest, j) => (j.digest_date && (!latest || j.digest_date > latest) ? j.digest_date : latest),
    null
  );

  // Previous days' matches, grouped by digest_date descending, capped at
  // the 5 most recent dates to keep the page light. Same JobCard as today
  // (feedback/apply/retry are per-match, so they all keep working).
  const historyByDate = new Map<string, UserJob[]>();
  for (const j of visibleJobs) {
    if (!j.digest_date || j.digest_date === today) continue;
    const list = historyByDate.get(j.digest_date) || [];
    list.push(j);
    historyByDate.set(j.digest_date, list);
  }
  const historyDates = Array.from(historyByDate.keys()).sort().reverse().slice(0, 5);
  const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().split("T")[0];
  const historyLabel = (d: string) =>
    d === yesterday
      ? "Yesterday"
      : new Date(`${d}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "long" });

  return (
    <main className="min-h-screen" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <nav className="px-6 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <BrandMark />
          <div className="text-right">
            <div className="text-sm font-medium" style={{ color: "var(--text)" }}>{user.name}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>{user.email}</div>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Greeting */}
        <div className="mb-8 animate-fade-in">
          <div className="flex items-center gap-2 mb-2">
            <Sun size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
            <span className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>
              {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}
            </span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold" style={{ color: "var(--text)" }}>
            Good morning, <span className="text-gradient">{firstName}</span>
          </h1>
          <p className="mt-2" style={{ color: "var(--text-muted)" }}>
            {jobsFound > 0
              ? `We found ${jobsFound} job${jobsFound > 1 ? "s" : ""} matching your profile today.`
              : "Your matches are being prepared — new jobs arrive every morning."}
          </p>
        </div>

        {/* Stat cards — all real, verifiable numbers */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 animate-fade-in">
          <StatCard icon={Briefcase} label="Jobs Found" value={jobsFound} />
          <StatCard
            icon={FileText}
            label="Resumes Ready"
            value={resumesReady}
            onClick={resumesReady > 0 ? () => setShowOnlyReady((v) => !v) : undefined}
            active={showOnlyReady}
          />
          <StatCard icon={Target} label="Best Match" value={`${bestMatch}%`} />
          <Card className="p-5">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
              <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Profile Strength</span>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <div className="text-2xl font-extrabold" style={{ color: "var(--text)" }}>
                {user.profile_strength ?? 0}%
              </div>
              {(user.profile_strength ?? 0) < 100 && (
                <a
                  href={`/profile?t=${encodeURIComponent(token)}`}
                  className="text-xs font-medium hover:underline"
                  style={{ color: "var(--primary)" }}
                >
                  Improve
                </a>
              )}
            </div>
          </Card>
        </div>

        {/* Delivery status + digest-time picker together at the TOP — the
            picker was previously buried below every job card, so users only
            discovered their delivery time after scrolling the whole page. */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-10 animate-fade-in">
          <Card className="p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-md shrink-0" style={{ background: "var(--surface-muted)" }}>
                <Clock size={18} strokeWidth={1.75} style={{ color: "var(--text-muted)" }} />
              </div>
              <div>
                <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {lastMatchDate ? `Last matches delivered ${lastMatchDate === today ? "today" : `on ${lastMatchDate}`}` : "No matches delivered yet"}
                </div>
                <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {allJobs.length > 0
                    ? `${allJobs.length} match${allJobs.length > 1 ? "es" : ""} delivered in total`
                    : "Matching runs after signup and every morning after that"}
                </div>
              </div>
            </div>
          </Card>
          <DigestTimePicker userId={user.id} token={token} currentTime={user.preferred_digest_time} />
        </div>

        {/* One-time location filter — narrows the view only, never the
            saved preferences. Options come from the loaded jobs, so it
            only appears once there's something to filter. */}
        {(locationOptions.length > 0 || hasRemote) && allJobs.length > 1 && (
          <div className="flex flex-wrap items-center gap-2 mb-6 animate-fade-in">
            <MapPin size={16} strokeWidth={1.75} style={{ color: "var(--text-muted)" }} />
            <select
              value={locationFilter}
              onChange={(e) => setLocationFilter(e.target.value)}
              className="px-3 py-2 rounded-md text-sm"
              style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
              aria-label="Filter matches by location"
            >
              <option value="">All locations</option>
              {hasRemote && <option value="__remote__">Remote</option>}
              {locationOptions.map((loc) => (
                <option key={loc} value={loc}>{loc}</option>
              ))}
            </select>
            {locationFilter && (
              <button
                type="button"
                onClick={() => setLocationFilter("")}
                className="text-sm font-medium hover:underline"
                style={{ color: "var(--primary)" }}
              >
                Clear
              </button>
            )}
            {locationFilter && (
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                Showing {visibleJobs.length} of {allJobs.length} matches
              </span>
            )}
          </div>
        )}

        {showOnlyReady ? (
          <>
            {/* Filtered view: only matches with a finished tailored resume */}
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold" style={{ color: "var(--text)" }}>
                Resumes ready ({resumesReady})
              </h2>
              <button
                type="button"
                onClick={() => setShowOnlyReady(false)}
                className="text-sm font-medium hover:underline"
                style={{ color: "var(--primary)" }}
              >
                Show all matches
              </button>
            </div>
            <div className="space-y-4">
              {readyMatches.map((m, i) => <JobCard key={m.id} match={m} index={i} userId={user.id} token={token} />)}
            </div>
          </>
        ) : (
          <>
            {/* Today's jobs */}
            <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--text)" }}>Today&apos;s matches</h2>
            {todayMatches.length > 0 ? (
              <div className="space-y-4">
                {todayDisplayed.map((m, i) => <JobCard key={m.id} match={m} index={i} userId={user.id} token={token} />)}
                {todayMatches.length > TODAY_DISPLAY_CAP && (
                  <button
                    type="button"
                    onClick={() => setShowAllToday((v) => !v)}
                    className="w-full py-3 rounded-lg text-sm font-medium border transition-colors hover:border-[var(--primary)]"
                    style={{ borderColor: "var(--border)", color: "var(--primary)" }}
                  >
                    {showAllToday
                      ? "Show fewer"
                      : `Show all ${todayMatches.length} matches from today`}
                  </button>
                )}
              </div>
            ) : locationFilter ? (
              // Filter emptied the list — say so instead of implying no
              // matches exist at all.
              <p className="text-sm mb-2" style={{ color: "var(--text-muted)" }}>
                No matches for this location today — clear the filter to see everything.
              </p>
            ) : historyDates.length > 0 ? (
              // No new matches today but there's history below — a slim note
              // beats a big empty card that pushes real content off-screen.
              <p className="text-sm mb-2" style={{ color: "var(--text-muted)" }}>
                No new matches yet today — new jobs arrive every morning. Your earlier matches are below.
              </p>
            ) : (
              <Card>
                <EmptyState
                  icon={Clock}
                  title="No matches yet today"
                  description="Your first matches are usually ready within a few minutes of signing up — try refreshing. After that, new matches arrive every morning."
                />
              </Card>
            )}

            {/* Your applications — user-asserted progress tracker */}
            {applications.length > 0 && (
              <div className="mt-10">
                <h2 className="text-lg font-semibold mb-1" style={{ color: "var(--text)" }}>Your applications</h2>
                <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
                  Jobs you marked as applied — update the status as things move.
                </p>
                <Card className="p-0 overflow-hidden">
                  {applications.map((m, i) => (
                    <div
                      key={m.id}
                      className="flex flex-wrap items-center justify-between gap-3 px-5 py-4"
                      style={i > 0 ? { borderTop: "1px solid var(--border)" } : undefined}
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-semibold truncate" style={{ color: "var(--text)" }}>{m.jobs.title}</p>
                        <p className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
                          {m.jobs.company}
                          {m.applied_at && ` · marked applied ${new Date(m.applied_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}`}
                        </p>
                      </div>
                      <ApplicationStatusSelect userId={user.id} token={token} match={m} />
                    </div>
                  ))}
                </Card>
              </div>
            )}

            {/* Previous days, one section per date, most recent first */}
            {historyDates.map((d) => (
              <div key={d} className="mt-10">
                <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--text)" }}>{historyLabel(d)}</h2>
                <div className="space-y-4">
                  {(historyByDate.get(d) || []).map((m, i) => (
                    <JobCard key={m.id} match={m} index={i} userId={user.id} token={token} />
                  ))}
                </div>
              </div>
            ))}
          </>
        )}

        <div className="mt-12">
          <InviteCard userId={user.id} />
        </div>

        <div className="mt-12 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          <p>New matches every morning</p>
          <p className="mt-1">
            Questions?{" "}
            <a href="mailto:gargeypatel123@gmail.com" className="hover:underline" style={{ color: "var(--primary)" }}>
              gargeypatel123@gmail.com
            </a>
          </p>
          <AiDisclosure />
        </div>
      </div>
    </main>
  );
}

export default function DashboardClient() {
  return (
    <Suspense fallback={<div className="min-h-screen" style={{ background: "var(--bg)" }} />}>
      <DashboardContent />
    </Suspense>
  );
}
