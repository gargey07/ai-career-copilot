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
  matches_total: number;
  matches_today: number;
  resumes_ready: number;
  applied: number;
  interviewing: number;
  offered: number;
  last_digest_date: string | null;
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
  error_message: string | null;
  sent_at: string | null;
}
interface Overview {
  generated_at: string;
  usage_date: string;
  totals: { users: number; active_users: number; jobs_in_pool: number; matches_delivered: number; apply_clicks: number };
  funnel: Funnel;
  api_usage: ApiUsageRow[];
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

function UsageBar({ row }: { row: ApiUsageRow }) {
  const capped = row.limit > 0;
  const pct = capped ? Math.min(100, Math.round((row.used / row.limit) * 100)) : 0;
  const barColor = pct >= 90 ? "var(--coral)" : pct >= 70 ? "var(--accent)" : "var(--success)";
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-sm font-medium" style={{ color: "var(--text)" }}>{row.label}</span>
        <span className="text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
          {capped ? `${row.used} / ${row.limit} today` : `${row.used} today · no cap`}
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

  const runPipeline = async () => {
    setPipelineRunning(true);
    setPipelineMsg("");
    try {
      const res = await fetch(`${API_URL}/api/admin/run-pipeline?token=${encodeURIComponent(token)}`, { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Couldn't start the pipeline.");
      setPipelineMsg(body.message || "Pipeline started.");
    } catch (e: any) {
      setPipelineMsg(e.message || "Couldn't start the pipeline.");
    } finally {
      setPipelineRunning(false);
    }
  };

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
                <div className="flex items-center gap-3">
                  <Button variant="secondary" onClick={runPipeline} disabled={pipelineRunning}>
                    <Play size={15} strokeWidth={1.75} />
                    {pipelineRunning ? "Starting…" : "Run pipeline now"}
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
                            <div className="flex flex-col gap-1">
                              <a
                                href={`/dashboard?user_id=${u.id}`}
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
                          <td className="px-2 py-2.5 text-xs" style={{ color: "var(--text-muted)" }}>
                            {row.status === "sent" ? row.subject : row.error_message || "—"}
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
