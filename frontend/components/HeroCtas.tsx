"use client";

import { useEffect, useState } from "react";
import { ArrowRight, LayoutDashboard } from "lucide-react";
import { getStoredProfile, type StoredProfile } from "@/lib/localProfile";

const DEMO_DASHBOARD_URL = "/dashboard?user_id=37c115cf-3cd5-4e06-be08-d9c60a1e489c";

// Hero buttons on the landing page. Returning users (profile already
// confirmed in this browser) get "Open my dashboard" as the secondary CTA
// instead of the demo dashboard.
export function HeroCtas() {
  const [stored, setStored] = useState<StoredProfile | null>(null);

  useEffect(() => {
    setStored(getStoredProfile());
  }, []);

  return (
    <>
      <div className="flex flex-col sm:flex-row gap-4 justify-center">
        <a
          href="/signup"
          className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-md font-bold text-white text-lg transition hover:opacity-90"
          style={{ background: "var(--primary)", boxShadow: "var(--shadow-e1)" }}
        >
          Join Free Beta — It&apos;s Free
          <ArrowRight size={18} strokeWidth={2} />
        </a>
        <a
          href={stored ? `/dashboard?user_id=${stored.id}` : DEMO_DASHBOARD_URL}
          className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-md font-semibold text-lg transition hover:bg-[var(--surface-muted)]"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
        >
          {stored && <LayoutDashboard size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />}
          {stored ? "Open my dashboard" : "View Demo Dashboard"}
        </a>
      </div>
      <p className="text-sm mt-4" style={{ color: "var(--text-muted)" }}>
        {stored
          ? `Welcome back${stored.name ? `, ${stored.name.split(" ")[0]}` : ""} — your profile is already set up.`
          : "Free during beta. No credit card required."}
      </p>
    </>
  );
}
