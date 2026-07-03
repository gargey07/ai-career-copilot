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
  type LucideIcon,
} from "lucide-react";
import { API_URL } from "@/lib/api";
import { getStoredProfile } from "@/lib/localProfile";
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
}
interface UserJob {
  id: string;
  match_score: number;
  pdf_url: string | null;
  digest_date: string;
  status: string;
  jobs: Job;
  feedback?: string | null;
  feedback_reason?: string | null;
  // Whether a resume was ever queued for this match at all — distinguishes
  // "not selected for AI tailoring" (normal — only top matches get one)
  // from "generation failed" (TICKET-020). See backend/api/routes/users.py.
  has_optimized_resume?: boolean;
}
interface User {
  id: string;
  name: string;
  email: string;
  target_roles: string[];
  profile_strength?: number;
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

// ── Score badge (CSS dot, no emoji) ─────────────────────────────────────────────
function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
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

// ── Resume feedback widget (thumbs up/down + reason chips) ─────────────────────
function ResumeFeedback({ userId, match }: { userId: string; match: UserJob }) {
  const [feedback, setFeedback] = useState<string | null>(match.feedback || null);
  const [pickingReason, setPickingReason] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (value: "up" | "down", reason = "") => {
    setSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/matches/${match.id}/feedback`, {
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

// ── Retry button for a failed/stuck PDF (TICKET-020) ────────────────────────────
// Never leave a permanent "Resume generating…" with no way out.
function RetryPdfButton({ userId, matchId }: { userId: string; matchId: string }) {
  const [state, setState] = useState<"idle" | "retrying" | "started">("idle");

  const retry = async () => {
    setState("retrying");
    try {
      const res = await fetch(`${API_URL}/api/users/${userId}/matches/${matchId}/retry-pdf`, { method: "POST" });
      setState(res.ok ? "started" : "idle");
    } catch {
      setState("idle");
    }
  };

  if (state === "started") {
    return (
      <span className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm" style={{ background: "var(--surface-muted)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
        <Clock size={16} strokeWidth={1.75} />
        Retrying — refresh in about a minute
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

// ── Job card ─────────────────────────────────────────────────────────────────────
function JobCard({ match, index, userId }: { match: UserJob; index: number; userId: string }) {
  const job = match.jobs;
  const hasApply = job.source_url && !job.source_url.includes("example.com");

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
        </div>
        <ScoreBadge score={match.match_score} />
      </div>

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
          <RetryPdfButton userId={userId} matchId={match.id} />
        ) : pdfInProgress ? (
          <span className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm" style={{ background: "var(--surface-muted)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
            <Clock size={16} strokeWidth={1.75} />
            Resume generating…
          </span>
        ) : null}

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
      </div>

      {match.pdf_url && (
        <div className="pt-3" style={{ borderTop: "1px solid var(--border)" }}>
          <ResumeFeedback userId={userId} match={match} />
        </div>
      )}
    </Card>
  );
}

// ── Loading skeleton ─────────────────────────────────────────────────────────────
function DashboardSkeleton() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-8">
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

// ── Dashboard Content ──────────────────────────────────────────────────────────
function DashboardContent() {
  const params = useSearchParams();
  const paramUserId = params.get("user_id");

  const [user, setUser] = useState<User | null>(null);
  const [allJobs, setAllJobs] = useState<UserJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const today = new Date().toISOString().split("T")[0];

  useEffect(() => {
    // No id in the URL? Fall back to the profile this browser confirmed
    // earlier — lets returning users just visit /dashboard directly.
    const userId = paramUserId || getStoredProfile()?.id;
    if (!userId) {
      setError("We don't know who you are yet — set up your profile first, or open the dashboard link from your email.");
      setLoading(false);
      return;
    }

    async function load() {
      try {
        const res = await fetch(`${API_URL}/api/users/${userId}/dashboard`);
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || "Failed to load dashboard.");
        }
        const data = await res.json();
        setUser(data.user);
        setAllJobs((data.jobs as any) || []);
      } catch (e: any) {
        setError(e.message || "Failed to load dashboard.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [paramUserId, today]);

  if (loading) {
    return (
      <main className="min-h-screen" style={{ background: "var(--bg)" }}>
        <DashboardSkeleton />
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
          <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>{error || "Invalid user ID. Check your link."}</p>
          <a
            href="/signup"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-semibold text-white transition hover:opacity-90"
            style={{ background: "var(--primary)" }}
          >
            Set up my profile
          </a>
        </Card>
      </main>
    );
  }

  const firstName = user.name?.split(" ")[0] || "there";
  const todayMatches = allJobs.filter((j) => j.digest_date === today);
  const jobsFound = todayMatches.length;
  const resumesReady = todayMatches.filter((m) => m.pdf_url).length;
  const bestMatch = todayMatches.length ? Math.round(Math.max(...todayMatches.map((m) => m.match_score)) * 100) : 0;
  // Last day we actually delivered matches — a real, verifiable metric
  // (strategy rule: never display applications/interviews/offers until we
  // can verify them).
  const lastMatchDate = allJobs.reduce<string | null>(
    (latest, j) => (j.digest_date && (!latest || j.digest_date > latest) ? j.digest_date : latest),
    null
  );

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
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6 animate-fade-in">
          <StatCard icon={Briefcase} label="Jobs Found" value={jobsFound} />
          <StatCard icon={FileText} label="Resumes Ready" value={resumesReady} />
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
                <a href="/signup" className="text-xs font-medium hover:underline" style={{ color: "var(--primary)" }}>
                  Improve
                </a>
              )}
            </div>
          </Card>
        </div>

        {/* Pipeline status — only real, verifiable info (see product strategy:
            no Applications/Interviews/Offers until we can actually track them). */}
        <Card className="p-5 mb-10 animate-fade-in">
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

        {/* Today's jobs */}
        <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--text)" }}>Today&apos;s matches</h2>
        {todayMatches.length > 0 ? (
          <div className="space-y-4">
            {todayMatches.map((m, i) => <JobCard key={m.id} match={m} index={i} userId={user.id} />)}
          </div>
        ) : (
          <Card>
            <EmptyState
              icon={Clock}
              title="No matches yet today"
              description="Your first matches are usually ready within a few minutes of signing up — try refreshing. After that, new matches arrive every morning."
            />
          </Card>
        )}

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
