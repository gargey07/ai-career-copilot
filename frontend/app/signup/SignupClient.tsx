"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LayoutDashboard, ArrowRight } from "lucide-react";
import UploadStep from "./UploadStep";
import ProfileEditor from "./ProfileEditor";
import { emptyProfile, type Profile } from "@/lib/profile";
import { BrandMark } from "@/components/BrandMark";
import { WarmBackend } from "@/components/WarmBackend";
import { getStoredProfile, saveStoredProfile, type StoredProfile } from "@/lib/localProfile";
import { trackEvent, captureRef, getRef } from "@/lib/analytics";

type Step = "upload" | "review";

export default function SignupClient() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("upload");
  const [profile, setProfile] = useState<Profile>(emptyProfile());
  const [resumeFilePath, setResumeFilePath] = useState<string | null>(null);
  const [returning, setReturning] = useState<StoredProfile | null>(null);

  // Someone who already confirmed a profile in this browser probably wants
  // their dashboard, not a second signup — offer the shortcut, don't force it.
  useEffect(() => {
    const existing = getStoredProfile();
    setReturning(existing);
    // Capture invite attribution whether they arrived here directly with
    // ?ref=... or picked it up on the landing page earlier this session.
    captureRef();
    // Funnel tracking (docs/PRODUCT_STRATEGY_BETA.md success metrics) —
    // only count genuinely new signup attempts, and only once per browser
    // session so a page reload doesn't inflate the "started" count.
    if (!existing && !sessionStorage.getItem("acc:funnel_started_logged")) {
      sessionStorage.setItem("acc:funnel_started_logged", "1");
      const ref = getRef();
      trackEvent("signup_started", ref ? { meta: { ref } } : undefined);
    }
  }, []);

  const handleUploadReady = (parsed: Profile, filePath: string | null) => {
    setProfile(parsed);
    setResumeFilePath(filePath);
    setStep("review");
    trackEvent("profile_review_reached");
  };

  const handleConfirmed = (id: string, name: string, dashboardToken: string) => {
    saveStoredProfile({ id, name, token: dashboardToken });
    trackEvent("signup_completed", { userId: id });
    router.push(`/success?name=${encodeURIComponent(name)}&t=${encodeURIComponent(dashboardToken)}`);
  };

  return (
    <main className="min-h-screen flex flex-col" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <WarmBackend />
      <nav className="flex items-center justify-between px-6 py-5 max-w-3xl mx-auto w-full">
        <BrandMark />
        <span className="text-sm" style={{ color: "var(--text-muted)" }}>Free Beta — No credit card</span>
      </nav>

      <div className="flex-1 flex items-start justify-center px-4 py-8">
        <div className="w-full max-w-2xl">
          {returning && step === "upload" && (
            <a
              href={returning.token ? `/dashboard?t=${encodeURIComponent(returning.token)}` : "/dashboard"}
              className="mb-6 flex items-center justify-between gap-3 rounded-lg px-5 py-4 transition hover:shadow-e2"
              style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-e1)" }}
            >
              <span className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-md shrink-0" style={{ background: "#FEF3C7" }}>
                  <LayoutDashboard size={18} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
                </span>
                <span className="text-sm" style={{ color: "var(--text)" }}>
                  <span className="font-semibold">
                    Welcome back{returning.name ? `, ${returning.name.split(" ")[0]}` : ""}.
                  </span>{" "}
                  <span style={{ color: "var(--text-muted)" }}>Your profile is already set up.</span>
                </span>
              </span>
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold shrink-0" style={{ color: "var(--primary)" }}>
                Open dashboard
                <ArrowRight size={15} strokeWidth={2} />
              </span>
            </a>
          )}
          <div className="text-center mb-8">
            <h1 className="text-3xl sm:text-4xl font-extrabold mb-3" style={{ color: "var(--text)" }}>
              Set up your <span className="text-gradient">profile</span>
            </h1>
            <p style={{ color: "var(--text-muted)" }}>
              {step === "upload"
                ? "Bring a resume, paste a link, or start from scratch."
                : "Takes 3 minutes. Your first matches start arriving right after you confirm."}
            </p>
          </div>

          {step === "upload" && <UploadStep onReady={handleUploadReady} />}
          {step === "review" && (
            <ProfileEditor initialProfile={profile} resumeFilePath={resumeFilePath} onConfirmed={handleConfirmed} />
          )}
        </div>
      </div>
    </main>
  );
}
