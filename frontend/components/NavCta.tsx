"use client";

import { useEffect, useState } from "react";
import { ArrowRight, LayoutDashboard } from "lucide-react";
import { getStoredProfile, type StoredProfile } from "@/lib/localProfile";

// Landing-nav call to action that knows whether this browser already has a
// confirmed profile. New visitors see "Join Free Beta"; returning users get
// a direct path to their dashboard (they can still reach signup from the hero).
export function NavCta() {
  const [stored, setStored] = useState<StoredProfile | null>(null);

  // Read localStorage after mount — server render must match the first client
  // render, so the default (signup CTA) is what both paint initially.
  useEffect(() => {
    setStored(getStoredProfile());
  }, []);

  if (stored) {
    return (
      <a
        href={`/dashboard?user_id=${stored.id}`}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-semibold text-white transition hover:opacity-90"
        style={{ background: "var(--primary)" }}
      >
        <LayoutDashboard size={16} strokeWidth={2} />
        Open Dashboard
      </a>
    );
  }

  return (
    <a
      href="/signup"
      className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-semibold text-white transition hover:opacity-90"
      style={{ background: "var(--primary)" }}
    >
      Join Free Beta
      <ArrowRight size={16} strokeWidth={2} />
    </a>
  );
}
