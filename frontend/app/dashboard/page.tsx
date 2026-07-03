"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabase";

// ── Types ──────────────────────────────────────────────────────────────────────
interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  is_remote: boolean;
  source_url: string;
  apply_url?: string;
}
interface UserJob {
  id: string;
  match_score: number;
  pdf_url: string | null;
  digest_date: string;
  status: string;
  feedback: string | null;
  feedback_reason: string | null;
  jobs: Job;
}
interface User {
  id: string;
  name: string;
  email: string;
  target_roles: string[];
  preferred_digest_time: string | null;
  last_digest_sent_at: string | null;
}

// ── Score badge — scores are 0–100 from new pgvector function ─────────────────
function ScoreBadge({ score }: { score: number }) {
  // Handle both old (0–1) and new (0–100) score formats
  const pct = score > 1 ? Math.round(score) : Math.round(score * 100);
  const cls =
    pct >= 85 ? "badge-green" :
    pct >= 70 ? "badge-yellow" :
    "badge-orange";
  const emoji = pct >= 85 ? "🟢" : pct >= 70 ? "🟡" : "🟠";
  return (
    <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold ${cls}`}>
      {emoji} {pct}% Match
    </span>
  );
}

// ── T-008: Feedback reasons (thumbs down chips) ───────────────────────────────
const FEEDBACK_REASONS = [
  "Wrong role",
  "Wrong location",
  "Too senior",
  "Too junior",
  "Company not a fit",
  "Already applied",
];

function FeedbackBar({
  matchId,
  currentFeedback,
  currentReason,
  onFeedbackChange,
}: {
  matchId: string;
  currentFeedback: string | null;
  currentReason: string | null;
  onFeedbackChange: (id: string, fb: string, reason?: string) => void;
}) {
  const [showReasons, setShowReasons] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submitFeedback(fb: string, reason?: string) {
    setSubmitting(true);
    try {
      await supabase
        .from("user_jobs")
        .update({
          feedback: fb,
          feedback_reason: reason || null,
          feedback_at: new Date().toISOString(),
        })
        .eq("id", matchId);
      onFeedbackChange(matchId, fb, reason);
    } finally {
      setSubmitting(false);
      setShowReasons(false);
    }
  }

  if (currentFeedback === "thumbs_up") {
    return (
      <div className="flex items-center gap-2 text-xs text-green-400 animate-fade-in">
        <span>👍</span>
        <span>Marked helpful</span>
        <button
          onClick={() => submitFeedback("")}
          className="text-gray-600 hover:text-gray-400 underline ml-1"
        >
          Undo
        </button>
      </div>
    );
  }

  if (currentFeedback === "thumbs_down") {
    return (
      <div className="flex items-center gap-2 text-xs text-red-400 animate-fade-in">
        <span>👎</span>
        <span>Marked not helpful{currentReason ? ` · ${currentReason}` : ""}</span>
        <button
          onClick={() => submitFeedback("")}
          className="text-gray-600 hover:text-gray-400 underline ml-1"
        >
          Undo
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-600">Was this match helpful?</span>
        <button
          disabled={submitting}
          onClick={() => submitFeedback("thumbs_up")}
          id={`feedback-up-${matchId}`}
          className="px-2.5 py-1 rounded-lg border border-white/10 hover:border-green-500/40 hover:bg-green-500/10 text-sm transition-all disabled:opacity-40"
          title="Good match"
        >
          👍
        </button>
        <button
          disabled={submitting}
          onClick={() => setShowReasons(!showReasons)}
          id={`feedback-down-${matchId}`}
          className="px-2.5 py-1 rounded-lg border border-white/10 hover:border-red-500/40 hover:bg-red-500/10 text-sm transition-all disabled:opacity-40"
          title="Not a good match"
        >
          👎
        </button>
      </div>
      {showReasons && (
        <div className="flex flex-wrap gap-2 animate-fade-in">
          {FEEDBACK_REASONS.map((reason) => (
            <button
              key={reason}
              onClick={() => submitFeedback("thumbs_down", reason)}
              disabled={submitting}
              className="px-3 py-1 rounded-full text-xs border border-white/10 hover:border-red-500/30 hover:bg-red-500/10 text-gray-400 hover:text-red-300 transition-all"
            >
              {reason}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Job Card ───────────────────────────────────────────────────────────────────
function JobCard({
  match,
  index,
  onFeedbackChange,
}: {
  match: UserJob;
  index: number;
  onFeedbackChange: (id: string, fb: string, reason?: string) => void;
}) {
  const job = match.jobs;
  const applyHref = job.apply_url || job.source_url;

  return (
    <div
      className="glass rounded-2xl p-6 space-y-4 hover:bg-white/[0.07] transition-all duration-200 animate-fade-in"
      style={{ animationDelay: `${index * 80}ms` }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-lg font-bold text-white">{job.title}</h3>
          <p className="text-gray-400 text-sm mt-0.5">
            {job.company}
            {job.location && ` · ${job.location}`}
            {job.is_remote && (
              <span className="ml-2 px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 text-xs border border-blue-500/20">
                Remote
              </span>
            )}
          </p>
        </div>
        <ScoreBadge score={match.match_score} />
      </div>

      {/* Status chip */}
      {match.status === "quality_failed" && (
        <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
          ⚠️ Resume optimization pending — will be ready in next digest
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-3">
        {match.pdf_url ? (
          <a
            href={match.pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            id={`job-resume-${match.id}`}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-sm font-semibold text-white transition-all"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            View Tailored Resume
          </a>
        ) : (
          <span className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-gray-500">
            📄 Resume generating...
          </span>
        )}

        {applyHref && !applyHref.includes("example.com") ? (
          <a
            href={applyHref}
            target="_blank"
            rel="noopener noreferrer"
            id={`job-apply-${match.id}`}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-white/15 hover:border-white/30 hover:bg-white/5 text-sm font-semibold text-white transition-all"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            Apply Now
          </a>
        ) : (
          <span className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-white/5 text-sm text-gray-600">
            Apply link coming soon
          </span>
        )}
      </div>

      {/* T-008: Feedback bar */}
      <div className="pt-2 border-t border-white/5">
        <FeedbackBar
          matchId={match.id}
          currentFeedback={match.feedback}
          currentReason={match.feedback_reason}
          onFeedbackChange={onFeedbackChange}
        />
      </div>
    </div>
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
  currentTime,
}: {
  userId: string;
  currentTime: string | null;
}) {
  const [selected, setSelected] = useState(currentTime || "07:00:00");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save(time: string) {
    setSaving(true);
    try {
      await supabase
        .from("users")
        .update({ preferred_digest_time: time })
        .eq("id", userId);
      setSelected(time);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="glass rounded-xl p-5 space-y-3">
      <div className="flex items-center gap-2">
        <span>⏰</span>
        <span className="text-sm font-semibold text-white">Daily Digest Time</span>
        {saved && <span className="text-xs text-green-400 animate-fade-in">Saved!</span>}
      </div>
      <div className="flex gap-2 flex-wrap">
        {TIME_SLOTS.map((slot) => (
          <button
            key={slot.value}
            disabled={saving}
            onClick={() => save(slot.value)}
            id={`digest-time-${slot.value.replace(/:/g, "")}`}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all border ${
              selected === slot.value
                ? "bg-blue-600 border-blue-500 text-white"
                : "bg-white/5 border-white/10 text-gray-400 hover:border-white/25 hover:text-white"
            }`}
          >
            {slot.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-600">Your digest will arrive around this time each morning (IST)</p>
    </div>
  );
}

// ── Empty State ────────────────────────────────────────────────────────────────
function EmptyState() {
  return (
    <div className="text-center py-24 animate-fade-in">
      <div className="text-6xl mb-6 animate-float inline-block">⏳</div>
      <h2 className="text-2xl font-bold text-white mb-3">No jobs yet today</h2>
      <p className="text-gray-400 max-w-md mx-auto">
        The pipeline runs nightly. Your first digest will arrive at your preferred time tomorrow morning.
        Check back then!
      </p>
    </div>
  );
}

// ── Dashboard Content ──────────────────────────────────────────────────────────
function DashboardContent() {
  const params = useSearchParams();
  const userId = params.get("user_id");

  const [user, setUser]       = useState<User | null>(null);
  const [matches, setMatches] = useState<UserJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");

  const today = new Date().toISOString().split("T")[0];

  useEffect(() => {
    if (!userId) { setError("No user ID in URL. Check your link."); setLoading(false); return; }

    async function load() {
      try {
        // Fetch user (including T-012 fields)
        const { data: userData, error: userErr } = await supabase
          .from("users")
          .select("id, name, email, target_roles, preferred_digest_time, last_digest_sent_at")
          .eq("id", userId)
          .single();
        if (userErr) throw userErr;
        setUser(userData);

        // Fetch today's job matches (including T-008 feedback fields)
        const { data: matchData, error: matchErr } = await supabase
          .from("user_jobs")
          .select("id, match_score, pdf_url, digest_date, status, feedback, feedback_reason, jobs(id, title, company, location, is_remote, source_url, apply_url)")
          .eq("user_id", userId)
          .eq("digest_date", today)
          .order("match_score", { ascending: false });
        if (matchErr) throw matchErr;
        setMatches((matchData as any) || []);
      } catch (e: any) {
        setError(e.message || "Failed to load dashboard.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [userId, today]);

  // T-008: Update feedback in local state without re-fetching
  function handleFeedbackChange(matchId: string, fb: string, reason?: string) {
    setMatches((prev) =>
      prev.map((m) =>
        m.id === matchId ? { ...m, feedback: fb, feedback_reason: reason || null } : m
      )
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4 animate-pulse">
          <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 mx-auto animate-spin" />
          <p className="text-gray-400">Loading your matches...</p>
        </div>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="glass rounded-2xl p-8 text-center max-w-md">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-xl font-bold text-white mb-2">Dashboard Error</h2>
          <p className="text-gray-400 text-sm">{error || "Invalid user ID. Check your link."}</p>
        </div>
      </div>
    );
  }

  const firstName = user.name.split(" ")[0];

  // Best match score — handle both 0–1 and 0–100 formats
  const bestScore = matches.length > 0
    ? Math.max(...matches.map((m) => m.match_score > 1 ? Math.round(m.match_score) : Math.round(m.match_score * 100)))
    : 0;

  return (
    <main className="min-h-screen">
      {/* Background */}
      <div className="fixed inset-0 -z-10 pointer-events-none">
        <div className="absolute top-0 left-0 w-[600px] h-[400px] rounded-full bg-blue-600/10 blur-[100px]" />
        <div className="absolute bottom-0 right-0 w-[500px] h-[400px] rounded-full bg-purple-600/10 blur-[100px]" />
      </div>

      {/* Nav */}
      <nav className="border-b border-white/5 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <a href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-sm font-bold">
              AI
            </div>
            <span className="font-semibold text-white">Career Copilot</span>
          </a>
          <div className="text-right">
            <div className="text-sm font-medium text-white">{user.name}</div>
            <div className="text-xs text-gray-500">{user.email}</div>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Header */}
        <div className="mb-10 animate-fade-in">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-2xl">☀️</span>
            <span className="text-sm text-blue-300 font-medium">
              Morning Digest — {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}
            </span>
          </div>
          <h1 className="text-4xl font-extrabold text-white">
            Good morning, <span className="text-gradient">{firstName}!</span>
          </h1>
          <p className="text-gray-400 mt-2">
            {matches.length > 0
              ? `We found ${matches.length} job${matches.length > 1 ? "s" : ""} for you today. Your AI has already tailored your resume for each one.`
              : "Your pipeline hasn't run yet today. Check back after your preferred digest time."}
          </p>
        </div>

        {/* Stats row */}
        {matches.length > 0 && (
          <div className="grid grid-cols-3 gap-4 mb-10 animate-fade-in">
            {[
              { label: "Jobs Today",    value: matches.length },
              { label: "Best Match",    value: `${bestScore}%` },
              { label: "Resumes Ready", value: matches.filter((m) => m.pdf_url).length },
            ].map((stat) => (
              <div key={stat.label} className="glass rounded-xl p-4 text-center">
                <div className="text-2xl font-extrabold text-white">{stat.value}</div>
                <div className="text-xs text-gray-500 mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Job Cards */}
        {matches.length > 0 ? (
          <div className="space-y-4">
            {matches.map((m, i) => (
              <JobCard
                key={m.id}
                match={m}
                index={i}
                onFeedbackChange={handleFeedbackChange}
              />
            ))}
          </div>
        ) : (
          <EmptyState />
        )}

        {/* T-012: Settings panel */}
        <div className="mt-12 space-y-4">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Preferences</h2>
          <DigestTimePicker
            userId={user.id}
            currentTime={user.preferred_digest_time}
          />
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-sm text-gray-600">
          <p>Pipeline runs nightly · New matches delivered at your preferred time</p>
          <p className="mt-1">
            Questions?{" "}
            <a href="mailto:gargeypatel123@gmail.com" className="text-blue-400 hover:underline">
              gargeypatel123@gmail.com
            </a>
          </p>
        </div>
      </div>
    </main>
  );
}

// ── Page Export ────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-gray-400">Loading...</div>}>
      <DashboardContent />
    </Suspense>
  );
}
