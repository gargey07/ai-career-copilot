"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ShieldCheck,
  Users,
  Briefcase,
  Gauge,
  Send,
  RefreshCw,
  Play,
  AlertTriangle,
  FileText,
  KeyRound,
  MousePointerClick,
  Trash2,
  Mail,
  type LucideIcon,
} from "lucide-react";
import { API_URL } from "@/lib/api";
import { BrandMark } from "@/components/BrandMark";
import { Card, SectionCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";

// ── Types (mirror GET /api/admin/overview) ─────────────────────────────────────
interface ApiUsageRow {
  service: string;
  label: string;
  limit: number; // 0 = uncapped
  used: number;
  failed?: number; // AI-waterfall failure count for this provider today
  key_configured?: boolean; // present only for key-gated services — omitted means "not applicable"
  key_length?: number; // validated (post-strip) length the app actually uses
  raw_env_length?: number | null; // raw os.environ length; null = variable not present on this container at all
}
interface AdminUserRow {
  id: string;
  name: string;
  email: string;
  joined_at: string | null;
  job_category: string;
  experience_level: string;
  is_active: boolean;
  has_resume: boolean;
  dashboard_token?: string;
  resume_quota_override?: number | null;
  job_count_override?: number | null;
  override_expires_at?: string | null;
  matches_total: number;
  matches_today: number;
  resumes_ready: number;
  applied: number;
  interviewing: number;
  offered: number;
  last_digest_date: string | null;
}
interface PoolJob {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  source: string | null;
  search_category?: string | null;
  collected_at: string | null;
  source_url: string | null;
}
interface Funnel {
  signup_started: number;
  profile_review_reached: number;
  signup_completed: number;
}
interface EmailLogRow {
  user_email: string;
  type: string;
  status: string;
  subject: string | null;
  provider: string | null;
  error_message: string | null;
  sent_at: string | null;
}
interface PdfEngineDiagnostic {
  configured: string;
  raw_env_length: number | null;
}
interface Overview {
  generated_at: string;
  usage_date: string;
  totals: { users: number; active_users: number; jobs_in_pool: number; matches_delivered: number; apply_clicks: number };
  funnel: Funnel;
  api_usage: ApiUsageRow[];
  pdf_engine?: PdfEngineDiagnostic;
  users: AdminUserRow[];
  email_history?: EmailLogRow[];
}

const TOKEN_KEY = "acc:admin_token";

// ── Small pieces ───────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string | number }) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>{label}</span>
      </div>
      <div className="text-2xl font-extrabold" style={{ color: "var(--text)" }}>{value}</div>
    </Card>
  );
}

// Two-click confirm (click once to arm, click again within a few seconds
// to actually delete) — avoids a native browser confirm() dialog while
// still making a destructive action require deliberate intent. Mainly
// for cleaning up test/dummy accounts created while trying the product.
function DeleteUserButton({ token, userId, email, onDeleted }: { token: string; userId: string; email: string; onDeleted: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!confirming) return;
    const t = setTimeout(() => setConfirming(false), 4000);
    return () => clearTimeout(t);
  }, [confirming]);

  const handleClick = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setDeleting(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/users/${userId}?token=${encodeURIComponent(token)}`, { method: "DELETE" });
      if (res.ok) onDeleted();
    } finally {
      setDeleting(false);
      setConfirming(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={deleting}
      title={confirming ? `Click again to permanently delete ${email}` : `Delete ${email}`}
      className="inline-flex items-center gap-1 text-xs font-medium hover:underline disabled:opacity-60"
      style={{ color: confirming ? "var(--coral)" : "var(--text-muted)" }}
    >
      <Trash2 size={12} strokeWidth={2} />
      {deleting ? "Deleting…" : confirming ? "Confirm delete?" : "Delete"}
    </button>
  );
}

// T-023: per-user limit overrides — blank = use the global default.
// Saves on Enter/blur only when a value actually changed.
function OverridesEditor({ token, user, onSaved }: { token: string; user: AdminUserRow; onSaved: () => void }) {
  const [resumeQuota, setResumeQuota] = useState(user.resume_quota_override?.toString() ?? "");
  const [jobCount, setJobCount] = useState(user.job_count_override?.toString() ?? "");
  const [expires, setExpires] = useState((user.override_expires_at ?? "").slice(0, 10));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const dirty =
    resumeQuota !== (user.resume_quota_override?.toString() ?? "") ||
    jobCount !== (user.job_count_override?.toString() ?? "") ||
    expires !== (user.override_expires_at ?? "").slice(0, 10);

  const save = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/users/${user.id}/overrides?token=${encodeURIComponent(token)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_quota_override: resumeQuota.trim() === "" ? null : Number(resumeQuota),
          job_count_override: jobCount.trim() === "" ? null : Number(jobCount),
          override_expires_at: expires.trim() === "" ? null : expires,
        }),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        onSaved();
      }
    } finally {
      setSaving(false);
    }
  };

  const inputCls = "w-12 px-1.5 py-1 rounded text-xs text-center outline-none focus:border-[var(--primary)]";
  const inputStyle = { border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)" };
  return (
    <div className="flex items-center gap-1.5" title="Per-user limits — resumes/day and jobs/day. Blank = default.">
      <input
        value={resumeQuota}
        onChange={(e) => setResumeQuota(e.target.value.replace(/[^0-9]/g, ""))}
        onBlur={save}
        onKeyDown={(e) => e.key === "Enter" && save()}
        placeholder="AI"
        className={inputCls}
        style={inputStyle}
        aria-label="Resume quota override"
      />
      <input
        value={jobCount}
        onChange={(e) => setJobCount(e.target.value.replace(/[^0-9]/g, ""))}
        onBlur={save}
        onKeyDown={(e) => e.key === "Enter" && save()}
        placeholder="jobs"
        className={inputCls}
        style={inputStyle}
        aria-label="Job count override"
      />
      <input
        type="date"
        value={expires}
        onChange={(e) => setExpires(e.target.value)}
        onBlur={save}
        className="px-1.5 py-1 rounded text-xs outline-none focus:border-[var(--primary)]"
        style={{ ...inputStyle, width: 118 }}
        aria-label="Override expiry date"
        title="Overrides auto-clear after this date. Blank = no expiry."
      />
      {saved && <span className="text-xs" style={{ color: "var(--success)" }}>✓</span>}
    </div>
  );
}

// T-023: search the shared jobs pool by title — the QA tool for
// "does category X actually return good jobs?"
function JobsPoolSearch({ token }: { token: string }) {
  const [q, setQ] = useState("");
  const [jobs, setJobs] = useState<PoolJob[] | null>(null);
  const [searching, setSearching] = useState(false);

  const search = async () => {
    setSearching(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/jobs?token=${encodeURIComponent(token)}&q=${encodeURIComponent(q)}`);
      if (res.ok) {
        const data = await res.json();
        setJobs(data.jobs || []);
      }
    } finally {
      setSearching(false);
    }
  };

  return (
    <div>
      <div className="flex gap-2 mb-4">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          placeholder="Search job titles… (empty = newest 50)"
          className="flex-1 px-3 py-2 rounded-md text-sm outline-none focus:border-[var(--primary)]"
          style={{ border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)" }}
        />
        <Button variant="secondary" onClick={search} disabled={searching}>
          {searching ? "Searching…" : "Search"}
        </Button>
      </div>
      {jobs !== null && (
        jobs.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>No jobs matched that title.</p>
        ) : (
          <div className="overflow-x-auto -mx-2">
            <table className="w-full text-sm" style={{ minWidth: 700 }}>
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                  <th className="px-2 py-2 font-semibold">Title</th>
                  <th className="px-2 py-2 font-semibold">Company</th>
                  <th className="px-2 py-2 font-semibold">Category</th>
                  <th className="px-2 py-2 font-semibold">Source</th>
                  <th className="px-2 py-2 font-semibold">Collected</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id} style={{ borderTop: "1px solid var(--border)" }}>
                    <td className="px-2 py-2.5 text-xs" style={{ color: "var(--text)" }}>
                      {j.source_url ? (
                        <a href={j.source_url} target="_blank" rel="noopener noreferrer" className="hover:underline" style={{ color: "var(--primary)" }}>
                          {j.title}
                        </a>
                      ) : j.title}
                    </td>
                    <td className="px-2 py-2.5 text-xs" style={{ color: "var(--text-muted)" }}>{j.company || "—"}</td>
                    <td className="px-2 py-2.5 text-xs" style={{ color: "var(--text-muted)" }}>{(j.search_category || "—").replace(/_/g, " ")}</td>
                    <td className="px-2 py-2.5 text-xs" style={{ color: "var(--text-muted)" }}>{j.source || "—"}</td>
                    <td className="px-2 py-2.5 text-xs whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                      {j.collected_at ? new Date(j.collected_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}

function FunnelBar({ funnel }: { funnel: Funnel }) {
  const stages: { key: keyof Funnel; label: string }[] = [
    { key: "signup_started", label: "Started signup" },
    { key: "profile_review_reached", label: "Reached review" },
    { key: "signup_completed", label: "Completed" },
  ];
  const base = funnel.signup_started || 0;

  if (base === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        No signup attempts logged yet — this fills in as new visitors reach /signup.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {stages.map((s) => {
        const count = funnel[s.key] || 0;
        const pct = Math.round((count / base) * 100);
        return (
          <div key={s.key}>
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="text-sm font-medium" style={{ color: "var(--text)" }}>{s.label}</span>
              <span className="text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>{count} ({pct}%)</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--surface-muted)" }}>
              <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: "var(--primary)" }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── PDF failures — the diagnostic behind every "resume shows Retry, does
// nothing" report. Lazy-loaded on demand (not part of the overview) since
// it's an occasional debugging tool, not something needed on every load.
interface PdfFailureRow {
  match_id: string;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  error: string | null;
  updated_at: string | null;
}

function PdfFailuresPanel({ token, pdfEngine }: { token: string; pdfEngine?: PdfEngineDiagnostic }) {
  const [rows, setRows] = useState<PdfFailureRow[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/pdf-failures?token=${encodeURIComponent(token)}`);
      const data = await res.json();
      setRows(res.ok ? data.failures : []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SectionCard
      icon={AlertTriangle}
      title="Recent PDF failures"
      action={
        <Button variant="secondary" onClick={load} disabled={loading}>
          <RefreshCw size={15} strokeWidth={1.75} className={loading ? "animate-spin" : ""} />
          {loading ? "Checking…" : rows === null ? "Check now" : "Refresh"}
        </Button>
      }
    >
      <PdfEngineBadge diagnostic={pdfEngine} />
      {rows === null ? (
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Click &quot;Check now&quot; to pull the most recent pdf_failed matches and their stored error text —
          the exact reason resumes are stuck, no Supabase access needed.
        </p>
      ) : rows.length === 0 ? (
        <EmptyState icon={FileText} title="No recent PDF failures" description="Every recent resume rendered successfully." />
      ) : (
        <div className="space-y-3">
          {rows.map((r) => (
            <div key={r.match_id} className="p-3 rounded-md" style={{ background: "var(--surface-muted)" }}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-medium" style={{ color: "var(--text)" }}>
                  {r.user_name || r.user_email || r.user_id}
                </span>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {r.updated_at ? new Date(r.updated_at).toLocaleString("en-IN") : ""}
                </span>
              </div>
              <p className="text-xs mt-1 font-mono break-words" style={{ color: "var(--coral)" }}>
                {r.error || "(no error text stored)"}
              </p>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// The exact diagnostic behind "PDF_ENGINE isn't set / got dropped in a
// migration" — same raw-vs-configured distinction as the API-key checks,
// surfaced at a glance instead of requiring a SQL query or log access.
function PdfEngineBadge({ diagnostic }: { diagnostic?: PdfEngineDiagnostic }) {
  if (!diagnostic) return null;
  const isWeasyprint = diagnostic.configured === "weasyprint";
  const envMissing = diagnostic.raw_env_length == null;
  const style = isWeasyprint
    ? { bg: "#DCFCE7", color: "#15803D", border: "#BBF7D0" }
    : { bg: "#FEE2E2", color: "#B91C1C", border: "#FECACA" };
  return (
    <div className="flex items-center gap-2 mb-4 text-xs">
      <span className="px-2 py-0.5 rounded-full font-semibold" style={{ background: style.bg, color: style.color, border: `1px solid ${style.border}` }}>
        PDF engine: {diagnostic.configured}
      </span>
      <span style={{ color: "var(--text-muted)" }}>
        {envMissing
          ? "PDF_ENGINE is not set on this server — using the code default."
          : `PDF_ENGINE is set (${diagnostic.raw_env_length} chars) on this server.`}
        {!isWeasyprint && " Chromium's system libraries are not installed in production — this will fail every PDF render."}
      </span>
    </div>
  );
}

function UsageBar({ row }: { row: ApiUsageRow }) {
  const capped = row.limit > 0;
  const pct = capped ? Math.min(100, Math.round((row.used / row.limit) * 100)) : 0;
  const barColor = pct >= 90 ? "var(--coral)" : pct >= 70 ? "var(--accent)" : "var(--success)";
  // A flat 0 usage with no failures is ambiguous — "not needed yet" and
  // "key missing" look identical. Only worth flagging when it's actually
  // suspicious: zero usage, key-gated, and the key genuinely isn't set.
  const keyMissing = row.key_configured === false && row.used === 0;
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-sm font-medium" style={{ color: "var(--text)" }}>{row.label}</span>
        <span className="text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
          {capped ? `${row.used} / ${row.limit} today` : `${row.used} today · no cap`}
          {(row.failed ?? 0) > 0 && (
            <span style={{ color: "var(--coral)" }}>{` · ${row.failed} failed`}</span>
          )}
          {keyMissing && (
            <span style={{ color: "var(--coral)" }}>
              {row.raw_env_length == null
                ? " · variable not present on this server at all — check the name in Coolify"
                : row.raw_env_length === 0
                ? " · variable is present but saved empty"
                : ` · variable has ${row.raw_env_length} char(s) but got stripped to 0 — likely just quotes/whitespace was pasted`}
            </span>
          )}
        </span>
      </div>
      <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--surface-muted)" }}>
        {capped && (
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${pct}%`, background: barColor }}
          />
        )}
      </div>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
      </div>
      <Skeleton className="h-64 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────
export default function AdminClient() {
  const [token, setToken] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pipelineMsg, setPipelineMsg] = useState("");
  const [pipelineRunning, setPipelineRunning] = useState(false);

  const load = useCallback(async (adminToken: string) => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/admin/overview?token=${encodeURIComponent(adminToken)}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        if (res.status === 403) sessionStorage.removeItem(TOKEN_KEY);
        throw new Error(body.detail || "Couldn't load the overview.");
      }
      setOverview(await res.json());
      setToken(adminToken);
      sessionStorage.setItem(TOKEN_KEY, adminToken);
    } catch (e: any) {
      setError(e.message || "Couldn't load the overview.");
      setOverview(null);
      setToken("");
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-use the token from this browser session so a refresh doesn't log you out.
  useEffect(() => {
    const saved = sessionStorage.getItem(TOKEN_KEY);
    if (saved) load(saved);
  }, [load]);

  // Shared by "Run pipeline now" and the two backfill triggers below — all
  // three are the same shape (POST, background job, one status message).
  const runAdminAction = async (endpoint: string, fallbackMsg: string) => {
    setPipelineRunning(true);
    setPipelineMsg("");
    try {
      const res = await fetch(`${API_URL}/api/admin/${endpoint}?token=${encodeURIComponent(token)}`, { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || fallbackMsg);
      setPipelineMsg(body.message || "Started.");
    } catch (e: any) {
      setPipelineMsg(e.message || fallbackMsg);
    } finally {
      setPipelineRunning(false);
    }
  };
  const runPipeline = () => runAdminAction("run-pipeline", "Couldn't start the pipeline.");
  const backfillExperience = () => runAdminAction("backfill-experience", "Couldn't start the experience backfill.");
  const backfillSeniority = () => runAdminAction("backfill-seniority", "Couldn't start the seniority backfill.");
  const classifyExperienceAi = () => runAdminAction("classify-experience-ai", "Couldn't start the AI classification.");

  // ── Locked state: ask for the token ──────────────────────────────────────────
  if (!token && !loading) {
    return (
      <main className="min-h-screen flex flex-col" style={{ background: "var(--bg)", color: "var(--text)" }}>
        <nav className="flex items-center justify-between px-6 py-5 max-w-4xl mx-auto w-full">
          <BrandMark />
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>Admin</span>
        </nav>
        <div className="flex-1 flex items-center justify-center px-4 pb-24">
          <div className="w-full max-w-sm">
            <SectionCard icon={KeyRound} title="Founder access">
              <p className="text-sm -mt-2 mb-4" style={{ color: "var(--text-muted)" }}>
                Paste the ADMIN_TOKEN you set on the server.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (tokenInput.trim()) load(tokenInput.trim());
                }}
                className="space-y-4"
              >
                <Field label="Admin token">
                  <Input
                    type="password"
                    value={tokenInput}
                    onChange={(e) => setTokenInput(e.target.value)}
                    placeholder="••••••••••••"
                    autoFocus
                  />
                </Field>
                {error && (
                  <div className="rounded-md px-4 py-3 text-sm flex items-start gap-2" style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "var(--coral)" }}>
                    <AlertTriangle size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" />
                    <span>{error}</span>
                  </div>
                )}
                <Button type="submit" variant="primary" className="w-full" disabled={!tokenInput.trim()}>
                  <ShieldCheck size={16} strokeWidth={1.75} />
                  Unlock
                </Button>
              </form>
            </SectionCard>
          </div>
        </div>
      </main>
    );
  }

  // ── Unlocked ─────────────────────────────────────────────────────────────────
  return (
    <main className="min-h-screen" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <nav className="px-6 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <BrandMark />
          <div className="flex items-center gap-3">
            <span
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold"
              style={{ background: "#FEF3C7", color: "#B45309", border: "1px solid #FDE68A" }}
            >
              <ShieldCheck size={13} strokeWidth={2} />
              Admin
            </span>
            <Button variant="secondary" onClick={() => load(token)} disabled={loading}>
              <RefreshCw size={15} strokeWidth={1.75} className={loading ? "animate-spin" : ""} />
              Refresh
            </Button>
          </div>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-6 py-10 space-y-8">
        {loading || !overview ? (
          <OverviewSkeleton />
        ) : (
          <>
            {/* Totals */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
              <StatCard icon={Users} label="Users" value={overview.totals.users} />
              <StatCard icon={Gauge} label="Active" value={overview.totals.active_users} />
              <StatCard icon={Briefcase} label="Jobs in pool" value={overview.totals.jobs_in_pool} />
              <StatCard icon={Send} label="Matches delivered" value={overview.totals.matches_delivered} />
              <StatCard icon={MousePointerClick} label="Apply clicks" value={overview.totals.apply_clicks} />
            </div>

            {/* Signup funnel — where people actually drop off, not just who finished */}
            <SectionCard icon={Users} title="Signup funnel">
              <FunnelBar funnel={overview.funnel} />
            </SectionCard>

            {/* API budgets */}
            <SectionCard
              icon={Gauge}
              title={`API usage today (${overview.usage_date})`}
              action={
                <div className="flex flex-wrap items-center gap-3">
                  <Button variant="secondary" onClick={runPipeline} disabled={pipelineRunning}>
                    <Play size={15} strokeWidth={1.75} />
                    {pipelineRunning ? "Starting…" : "Run pipeline now"}
                  </Button>
                  {/* One-time-ish backfills for the existing job pool — safe to
                      re-run (only touches NULL rows). Re-run experience after
                      any change to experience_months_from_text's regex. */}
                  <Button variant="secondary" onClick={backfillExperience} disabled={pipelineRunning}>
                    Backfill experience
                  </Button>
                  <Button variant="secondary" onClick={backfillSeniority} disabled={pipelineRunning}>
                    Backfill seniority
                  </Button>
                  {/* AI fallback for whatever's left after the two free
                      backfills above — phrasing like "recent graduates
                      welcome" that no regex/keyword list can enumerate.
                      Budget-capped (job_classify_daily_limit), safe to re-run. */}
                  <Button variant="secondary" onClick={classifyExperienceAi} disabled={pipelineRunning}>
                    Classify experience (AI)
                  </Button>
                </div>
              }
            >
              <div className="space-y-5">
                {overview.api_usage.map((row) => <UsageBar key={row.service} row={row} />)}
              </div>
              {pipelineMsg && (
                <p className="mt-5 text-sm rounded-md px-4 py-3" style={{ background: "var(--surface-muted)", color: "var(--text)" }}>
                  {pipelineMsg}
                </p>
              )}
            </SectionCard>

            <PdfFailuresPanel token={token} pdfEngine={overview.pdf_engine} />

            {/* Users */}
            <SectionCard icon={Users} title="Users">
              {overview.users.length === 0 ? (
                <EmptyState
                  icon={Users}
                  title="No users yet"
                  description="Signups will show up here the moment someone confirms a profile."
                />
              ) : (
                <div className="overflow-x-auto -mx-2">
                  <table className="w-full text-sm" style={{ minWidth: 900 }}>
                    <thead>
                      <tr className="text-left text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                        <th className="px-2 py-2 font-semibold">User</th>
                        <th className="px-2 py-2 font-semibold">Category</th>
                        <th className="px-2 py-2 font-semibold">Resume</th>
                        <th className="px-2 py-2 font-semibold text-right">Today</th>
                        <th className="px-2 py-2 font-semibold text-right">Total</th>
                        <th className="px-2 py-2 font-semibold text-right">PDFs</th>
                        <th className="px-2 py-2 font-semibold text-right">Applied</th>
                        <th className="px-2 py-2 font-semibold text-right">Interviews</th>
                        <th className="px-2 py-2 font-semibold text-right">Offers</th>
                        <th className="px-2 py-2 font-semibold">Last digest</th>
                        <th className="px-2 py-2 font-semibold" title="Per-user limits: AI resumes/day · jobs/day (blank = default)">Limits</th>
                        <th className="px-2 py-2 font-semibold" />
                      </tr>
                    </thead>
                    <tbody>
                      {overview.users.map((u) => (
                        <tr key={u.id} style={{ borderTop: "1px solid var(--border)" }}>
                          <td className="px-2 py-3">
                            <div className="font-medium" style={{ color: "var(--text)" }}>{u.name}</div>
                            <div className="text-xs" style={{ color: "var(--text-muted)" }}>{u.email}</div>
                          </td>
                          <td className="px-2 py-3" style={{ color: "var(--text-muted)" }}>
                            {u.job_category.replace(/_/g, " ")}
                          </td>
                          <td className="px-2 py-3">
                            {u.has_resume ? (
                              <span className="inline-flex items-center gap-1 text-xs font-medium" style={{ color: "var(--success)" }}>
                                <FileText size={13} strokeWidth={2} /> Uploaded
                              </span>
                            ) : (
                              <span className="text-xs" style={{ color: "var(--text-muted)" }}>Manual</span>
                            )}
                          </td>
                          <td className="px-2 py-3 text-right tabular-nums" style={{ color: "var(--text)" }}>{u.matches_today}</td>
                          <td className="px-2 py-3 text-right tabular-nums" style={{ color: "var(--text)" }}>{u.matches_total}</td>
                          <td className="px-2 py-3 text-right tabular-nums" style={{ color: "var(--text)" }}>{u.resumes_ready}</td>
                          <td className="px-2 py-3 text-right tabular-nums" style={{ color: "var(--text)" }}>{u.applied}</td>
                          <td className="px-2 py-3 text-right tabular-nums" style={{ color: "var(--text)" }}>{u.interviewing}</td>
                          <td className="px-2 py-3 text-right tabular-nums" style={{ color: "var(--text)" }}>{u.offered}</td>
                          <td className="px-2 py-3 text-xs" style={{ color: "var(--text-muted)" }}>{u.last_digest_date || "—"}</td>
                          <td className="px-2 py-3">
                            <OverridesEditor token={token} user={u} onSaved={() => load(token)} />
                          </td>
                          <td className="px-2 py-3">
                            <div className="flex flex-col gap-1">
                              <a
                                href={u.dashboard_token ? `/dashboard?t=${encodeURIComponent(u.dashboard_token)}` : "/dashboard"}
                                className="text-xs font-medium hover:underline"
                                style={{ color: "var(--primary)" }}
                              >
                                View dashboard
                              </a>
                              <a
                                href={`/admin/inspect?user_id=${u.id}`}
                                className="text-xs font-medium hover:underline"
                                style={{ color: "var(--text-muted)" }}
                                title="See the real matches + AI resume text for this user"
                              >
                                Inspect quality
                              </a>
                              <DeleteUserButton token={token} userId={u.id} email={u.email} onDeleted={() => load(token)} />
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>

            {/* Email history — did each digest actually go out? (T-015) */}
            {/* Jobs pool search (T-023) — QA the fetchers per category */}
            <SectionCard icon={Briefcase} title="Jobs pool">
              <JobsPoolSearch token={token} />
            </SectionCard>

            <SectionCard icon={Mail} title="Recent emails">
              {!overview.email_history || overview.email_history.length === 0 ? (
                <EmptyState
                  icon={Mail}
                  title="No emails logged yet"
                  description="Every digest attempt (sent or failed) will appear here."
                />
              ) : (
                <div className="overflow-x-auto -mx-2">
                  <table className="w-full text-sm" style={{ minWidth: 640 }}>
                    <thead>
                      <tr className="text-left text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                        <th className="px-2 py-2 font-semibold">Sent at</th>
                        <th className="px-2 py-2 font-semibold">To</th>
                        <th className="px-2 py-2 font-semibold">Type</th>
                        <th className="px-2 py-2 font-semibold">Status</th>
                        <th className="px-2 py-2 font-semibold">Via</th>
                        <th className="px-2 py-2 font-semibold">Detail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.email_history.map((row, i) => (
                        <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                          <td className="px-2 py-2.5 text-xs whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                            {row.sent_at ? new Date(row.sent_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"}
                          </td>
                          <td className="px-2 py-2.5 text-xs" style={{ color: "var(--text)" }}>{row.user_email}</td>
                          <td className="px-2 py-2.5 text-xs" style={{ color: "var(--text-muted)" }}>{row.type?.replace(/_/g, " ")}</td>
                          <td className="px-2 py-2.5">
                            <span
                              className="text-xs font-semibold"
                              style={{ color: row.status === "sent" ? "var(--success)" : "var(--coral)" }}
                            >
                              {row.status}
                            </span>
                          </td>
                          <td className="px-2 py-2.5 text-xs" style={{ color: "var(--text-muted)" }}>{row.provider || "—"}</td>
                          <td className="px-2 py-2.5 text-xs" style={{ color: "var(--text-muted)" }}>
                            <div>{row.subject || "—"}</div>
                            {row.error_message && (
                              <div
                                className="mt-0.5"
                                style={{ color: row.status === "sent" ? "var(--text-muted)" : "var(--coral)" }}
                                title={row.status === "sent" ? "Provider's acceptance response — proves the message was actually accepted for delivery, not just that the API call didn't error" : "Failure detail"}
                              >
                                {row.error_message}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>
          </>
        )}
      </div>
    </main>
  );
}
