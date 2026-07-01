"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Search, Sparkles, FileText, Mail, ArrowRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const TIMELINE: { time: string; icon: LucideIcon; desc: string }[] = [
  { time: "Tonight 2 AM", icon: Search, desc: "Our AI scans 5+ job boards and finds fresh roles for you." },
  { time: "Tonight 6 AM", icon: Sparkles, desc: "Gemini matches the best jobs to your exact profile." },
  { time: "Tonight 6:30 AM", icon: FileText, desc: "AI rewrites your resume tailored for each job." },
  { time: "Tomorrow 7 AM", icon: Mail, desc: "Digest lands in your inbox — ready to apply in 2 minutes." },
];

function SuccessContent() {
  const params = useSearchParams();
  const name = params.get("name") || "Friend";
  const id = params.get("id") || "";

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-12" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <div className="max-w-lg w-full text-center animate-fade-in space-y-8">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-2xl" style={{ background: "#ECFDF5" }}>
          <CheckCircle2 size={40} strokeWidth={1.75} style={{ color: "var(--success)" }} />
        </div>

        <div>
          <h1 className="text-4xl md:text-5xl font-extrabold mb-3" style={{ color: "var(--text)" }}>
            You&apos;re in, <span className="text-gradient">{name.split(" ")[0]}!</span>
          </h1>
          <p className="text-lg" style={{ color: "var(--text-muted)" }}>
            Your profile is live. The AI is already learning your preferences.
          </p>
        </div>

        <div className="rounded-lg p-8 text-left space-y-5" style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-e1)" }}>
          <h2 className="font-semibold text-lg" style={{ color: "var(--text)" }}>What happens next</h2>
          {TIMELINE.map((item) => (
            <div key={item.time} className="flex items-start gap-4">
              <div className="flex-shrink-0 flex h-9 w-9 items-center justify-center rounded-md" style={{ background: "#FEF3C7" }}>
                <item.icon size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
              </div>
              <div>
                <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>{item.time}</div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>{item.desc}</div>
              </div>
            </div>
          ))}
        </div>

        {id && (
          <div className="rounded-lg p-6 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-e1)" }}>
            <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
              Bookmark your personal dashboard — check your matches anytime:
            </p>
            <a
              href={`/dashboard?user_id=${id}`}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-md font-semibold text-white transition hover:opacity-90 text-sm"
              style={{ background: "var(--primary)", boxShadow: "var(--shadow-e1)" }}
            >
              Open My Dashboard
              <ArrowRight size={16} strokeWidth={2} />
            </a>
          </div>
        )}

        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Email us at{" "}
          <a href="mailto:gargeypatel123@gmail.com" className="hover:underline" style={{ color: "var(--primary)" }}>
            gargeypatel123@gmail.com
          </a>{" "}
          if you have questions.
        </p>
      </div>
    </main>
  );
}

export default function SuccessPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center" style={{ color: "var(--text-muted)" }}>Loading…</div>}>
      <SuccessContent />
    </Suspense>
  );
}
