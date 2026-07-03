"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  AlertTriangle,
  User,
  Briefcase,
  FileText,
  Mail,
  ExternalLink,
} from "lucide-react";
import { API_URL } from "@/lib/api";
import { BrandMark } from "@/components/BrandMark";
import { Card, SectionCard } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

// This page exists to answer one question the admin overview can't: is the
// output actually GOOD? Real matches, real job descriptions, real
// AI-optimized resume text — side by side, so a human can judge quality
// instead of just counting rows.

interface Job {
  title?: string;
  company?: string;
  location?: string;
  description?: string;
  source?: string;
  source_url?: string;
}
interface Match {
  id: string;
  match_score: number;
  status: string;
  digest_date: string;
  pdf_url: string | null;
  job: Job;
  optimized_resume_text: string | null;
  cover_letter_text: string | null;
  feedback?: string | null;
  feedback_reason?: string | null;
  click_count?: number;
}
interface InspectUser {
  id: string;
  name: string;
  email: string;
  job_category: string;
  experience_level: string;
  target_roles: string[];
  skills: string[];
  tools: string[];
  summary: string;
  resume_text: string;
  resume_template: string;
  created_at: string;
}
interface InspectData {
  user: InspectUser;
  matches: Match[];
}

function ScorePct({ score }: { score: number }) {
  const pct = Math.round((score || 0) * 100);
  const color = pct >= 80 ? "var(--success)" : pct >= 60 ? "var(--primary)" : "var(--accent)";
  return (
    <span className="text-sm font-bold tabular-nums" style={{ color }}>
      {pct}% match
    </span>
  );
}

function InspectContent() {
  const params = useSearchParams();
  const userId = params.get("user_id") || "";
  const [token, setToken] = useState("");
  const [data, setData] = useState<InspectData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const saved = sessionStorage.getItem("acc:admin_token") || "";
    setToken(saved);
    if (!userId) {
      setError("No user_id in the URL.");
      setLoading(false);
      return;
    }
    if (!saved) {
      setError("No admin token found — open /admin first and unlock it there.");
      setLoading(false);
      return;
    }
    fetch(`${API_URL}/api/admin/users/${userId}/inspect?token=${encodeURIComponent(saved)}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || "Couldn't load inspect data.");
        }
        return res.json();
      })
      .then(setData)
      .catch((e) => setError(e.message || "Couldn't load inspect data."))
      .finally(() => setLoading(false));
  }, [userId]);

  return (
    <main className="min-h-screen" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <nav className="px-6 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <BrandMark />
          <a href="/admin" className="inline-flex items-center gap-1.5 text-sm font-medium hover:underline" style={{ color: "var(--primary)" }}>
            <ArrowLeft size={15} strokeWidth={2} />
            Back to admin
          </a>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-10 space-y-6">
        {loading && (
          <div className="space-y-4">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-48 w-full" />
          </div>
        )}

        {!loading && error && (
          <Card className="p-6 flex items-start gap-3">
            <AlertTriangle size={20} strokeWidth={1.75} style={{ color: "var(--coral)" }} className="shrink-0 mt-0.5" />
            <p className="text-sm" style={{ color: "var(--text)" }}>{error}</p>
          </Card>
        )}

        {!loading && data && (
          <>
            <SectionCard icon={User} title={data.user.name || "(no name)"}>
              <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
                <div><span style={{ color: "var(--text-muted)" }}>Email:</span> {data.user.email}</div>
                <div><span style={{ color: "var(--text-muted)" }}>Category:</span> {data.user.job_category || "—"}</div>
                <div><span style={{ color: "var(--text-muted)" }}>Experience:</span> {data.user.experience_level || "—"}</div>
                <div><span style={{ color: "var(--text-muted)" }}>Template:</span> {data.user.resume_template || "modern"}</div>
                <div className="sm:col-span-2">
                  <span style={{ color: "var(--text-muted)" }}>Target roles:</span> {(data.user.target_roles || []).join(", ") || "—"}
                </div>
                <div className="sm:col-span-2">
                  <span style={{ color: "var(--text-muted)" }}>Skills:</span> {(data.user.skills || []).join(", ") || "—"}
                </div>
                <div className="sm:col-span-2">
                  <span style={{ color: "var(--text-muted)" }}>Tools:</span> {(data.user.tools || []).join(", ") || "—"}
                </div>
              </div>
              {data.user.summary && (
                <p className="mt-3 pt-3 text-sm" style={{ borderTop: "1px solid var(--border)", color: "var(--text-muted)" }}>
                  {data.user.summary}
                </p>
              )}
            </SectionCard>

            <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              {data.matches.length} match{data.matches.length !== 1 ? "es" : ""} — judge whether these actually fit the profile above
            </div>

            {data.matches.length === 0 && (
              <Card className="p-6 text-sm" style={{ color: "var(--text-muted)" }}>
                No matches yet for this user.
              </Card>
            )}

            {data.matches.map((m) => (
              <Card key={m.id} className="p-6 space-y-4">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div>
                    <div className="flex items-center gap-2">
                      <Briefcase size={16} strokeWidth={1.75} style={{ color: "var(--text-muted)" }} />
                      <span className="font-semibold" style={{ color: "var(--text)" }}>{m.job.title || "(untitled)"}</span>
                    </div>
                    <div className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {m.job.company} {m.job.location ? `· ${m.job.location}` : ""} {m.job.source ? `· via ${m.job.source}` : ""}
                    </div>
                    <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                      {m.digest_date} · status: {m.status}
                      {(m.click_count ?? 0) > 0 && ` · ${m.click_count} apply click${m.click_count === 1 ? "" : "s"}`}
                      {m.feedback && ` · feedback: ${m.feedback}${m.feedback_reason ? ` (${m.feedback_reason.replace(/_/g, " ")})` : ""}`}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <ScorePct score={m.match_score} />
                    {m.job.source_url && (
                      <a href={m.job.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs hover:underline" style={{ color: "var(--primary)" }}>
                        View posting <ExternalLink size={11} strokeWidth={2} />
                      </a>
                    )}
                  </div>
                </div>

                {m.job.description && (
                  <details>
                    <summary className="text-xs font-medium cursor-pointer" style={{ color: "var(--text-muted)" }}>
                      Job description ({m.job.description.length} chars)
                    </summary>
                    <p className="mt-2 text-xs whitespace-pre-wrap leading-relaxed p-3 rounded-md" style={{ background: "var(--surface-muted)", color: "var(--text-muted)", maxHeight: 200, overflowY: "auto" }}>
                      {m.job.description}
                    </p>
                  </details>
                )}

                {m.optimized_resume_text ? (
                  <div>
                    <button
                      type="button"
                      onClick={() => setExpanded((e) => ({ ...e, [m.id]: !e[m.id] }))}
                      className="inline-flex items-center gap-1.5 text-xs font-medium"
                      style={{ color: "var(--primary)" }}
                    >
                      <FileText size={13} strokeWidth={2} />
                      {expanded[m.id] ? "Hide" : "Show"} AI-optimized resume text
                    </button>
                    {expanded[m.id] && (
                      <pre className="mt-2 text-xs whitespace-pre-wrap leading-relaxed p-3 rounded-md font-sans" style={{ background: "var(--surface-muted)", color: "var(--text)", maxHeight: 400, overflowY: "auto" }}>
                        {m.optimized_resume_text}
                      </pre>
                    )}
                  </div>
                ) : (
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>No optimized resume yet for this match.</div>
                )}

                {m.cover_letter_text && (
                  <div>
                    <button
                      type="button"
                      onClick={() => setExpanded((e) => ({ ...e, [`${m.id}-cl`]: !e[`${m.id}-cl`] }))}
                      className="inline-flex items-center gap-1.5 text-xs font-medium"
                      style={{ color: "var(--primary)" }}
                    >
                      <Mail size={13} strokeWidth={2} />
                      {expanded[`${m.id}-cl`] ? "Hide" : "Show"} cover letter
                    </button>
                    {expanded[`${m.id}-cl`] && (
                      <pre className="mt-2 text-xs whitespace-pre-wrap leading-relaxed p-3 rounded-md font-sans" style={{ background: "var(--surface-muted)", color: "var(--text)", maxHeight: 300, overflowY: "auto" }}>
                        {m.cover_letter_text}
                      </pre>
                    )}
                  </div>
                )}
              </Card>
            ))}
          </>
        )}
      </div>
    </main>
  );
}

export default function InspectClient() {
  return (
    <Suspense fallback={<div className="min-h-screen" style={{ background: "var(--bg)" }} />}>
      <InspectContent />
    </Suspense>
  );
}
