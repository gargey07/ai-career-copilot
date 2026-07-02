"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Target, FileText, MousePointerClick, LayoutDashboard, ArrowRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { saveStoredProfile } from "@/lib/localProfile";

// Sell the outcome, not the implementation. No pipeline internals, no invented
// numbers, no promises about features that aren't live (trust rule in
// docs/PRODUCT_STRATEGY_BETA.md).
const OUTCOMES: { icon: LucideIcon; text: string }[] = [
  { icon: Target, text: "Curated job matches picked for your profile" },
  { icon: FileText, text: "ATS-tailored resumes for your top matches — rolling out during beta" },
  { icon: MousePointerClick, text: "One-click, apply-ready links" },
];

function SuccessContent() {
  const params = useSearchParams();
  const name = params.get("name") || "Friend";
  const id = params.get("id") || "";

  // Remember this browser's profile so the landing page, signup page, and
  // logo all route back to the dashboard on the next visit.
  useEffect(() => {
    if (id) saveStoredProfile({ id, name });
  }, [id, name]);

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
            Your profile is live. Everything from here is automatic.
          </p>
        </div>

        <div className="rounded-lg p-8 text-left" style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-e1)" }}>
          <h2 className="font-semibold text-lg mb-5" style={{ color: "var(--text)" }}>
            Your Copilot is already working on:
          </h2>
          <div className="space-y-4">
            {OUTCOMES.map((o) => (
              <div key={o.text} className="flex items-center gap-3">
                <div className="flex-shrink-0 flex h-9 w-9 items-center justify-center rounded-md" style={{ background: "#FEF3C7" }}>
                  <o.icon size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
                </div>
                <span className="text-sm" style={{ color: "var(--text)" }}>{o.text}</span>
              </div>
            ))}
          </div>
          <div className="mt-6 pt-5 flex items-center gap-2" style={{ borderTop: "1px solid var(--border)" }}>
            <LayoutDashboard size={18} strokeWidth={1.75} style={{ color: "var(--text-muted)" }} />
            <span className="text-sm font-medium" style={{ color: "var(--text)" }}>Fresh matches on your dashboard every morning.</span>
          </div>
        </div>

        {id && (
          <div className="rounded-lg p-6 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-e1)" }}>
            <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
              Your first matches are being prepared right now — they usually appear within a few minutes.
            </p>
            <a
              href={`/dashboard?user_id=${id}`}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-md font-semibold text-white transition hover:opacity-90 text-sm"
              style={{ background: "var(--primary)", boxShadow: "var(--shadow-e1)" }}
            >
              Open Dashboard
              <ArrowRight size={16} strokeWidth={2} />
            </a>
          </div>
        )}

        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Questions? Email{" "}
          <a href="mailto:gargeypatel123@gmail.com" className="hover:underline" style={{ color: "var(--primary)" }}>
            gargeypatel123@gmail.com
          </a>
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
