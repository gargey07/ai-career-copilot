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
}
interface UserJob {
  id: string;
  match_score: number;
  pdf_url: string | null;
  digest_date: string;
  status: string;
  jobs: Job;
}
interface User {
  id: string;
  name: string;
  email: string;
  target_roles: string[];
}

// ── Score badge helper ─────────────────────────────────────────────────────────
function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
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

// ── Job Card ───────────────────────────────────────────────────────────────────
function JobCard({ match, index }: { match: UserJob; index: number }) {
  const job = match.jobs;

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

      {/* Buttons */}
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

        {job.source_url && !job.source_url.includes("example.com") ? (
          <a
            href={job.source_url}
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
        The pipeline runs nightly at 2 AM. Your first digest will arrive tomorrow morning at 7 AM.
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
        // Fetch user
        const { data: userData, error: userErr } = await supabase
          .from("users")
          .select("id, name, email, target_roles")
          .eq("id", userId)
          .single();
        if (userErr) throw userErr;
        setUser(userData);

        // Fetch today's job matches
        const { data: matchData, error: matchErr } = await supabase
          .from("user_jobs")
          .select("id, match_score, pdf_url, digest_date, status, jobs(id, title, company, location, is_remote, source_url)")
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
              : "Your pipeline hasn't run yet today. Check back after 7 AM."}
          </p>
        </div>

        {/* Stats row */}
        {matches.length > 0 && (
          <div className="grid grid-cols-3 gap-4 mb-10 animate-fade-in">
            {[
              { label: "Jobs Today",       value: matches.length },
              { label: "Best Match",       value: `${Math.round(Math.max(...matches.map(m => m.match_score)) * 100)}%` },
              { label: "Resumes Ready",    value: matches.filter(m => m.pdf_url).length },
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
            {matches.map((m, i) => <JobCard key={m.id} match={m} index={i} />)}
          </div>
        ) : (
          <EmptyState />
        )}

        {/* Footer note */}
        <div className="mt-12 text-center text-sm text-gray-600">
          <p>Pipeline runs nightly at 2 AM · New matches delivered by 7 AM</p>
          <p className="mt-1">Questions? <a href="mailto:gargeypatel123@gmail.com" className="text-blue-400 hover:underline">gargeypatel123@gmail.com</a></p>
        </div>
      </div>
    </main>
  );
}

// ── Page Export ────────────────────────────────────────────────────────────────
export default function DashboardClient() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-gray-400">Loading...</div>}>
      <DashboardContent />
    </Suspense>
  );
}
