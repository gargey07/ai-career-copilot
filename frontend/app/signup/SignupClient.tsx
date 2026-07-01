"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import UploadStep from "./UploadStep";
import ProfileEditor from "./ProfileEditor";
import { emptyProfile, type Profile } from "@/lib/profile";
import { BrandMark } from "@/components/BrandMark";

type Step = "upload" | "review";

export default function SignupClient() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("upload");
  const [profile, setProfile] = useState<Profile>(emptyProfile());
  const [resumeFilePath, setResumeFilePath] = useState<string | null>(null);

  const handleUploadReady = (parsed: Profile, filePath: string | null) => {
    setProfile(parsed);
    setResumeFilePath(filePath);
    setStep("review");
  };

  const handleConfirmed = (id: string, name: string) => {
    router.push(`/success?name=${encodeURIComponent(name)}&id=${id}`);
  };

  return (
    <main className="min-h-screen flex flex-col" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <nav className="flex items-center justify-between px-6 py-5 max-w-3xl mx-auto w-full">
        <BrandMark />
        <span className="text-sm" style={{ color: "var(--text-muted)" }}>Free Beta — No credit card</span>
      </nav>

      <div className="flex-1 flex items-start justify-center px-4 py-8">
        <div className="w-full max-w-2xl">
          <div className="text-center mb-8">
            <h1 className="text-3xl sm:text-4xl font-extrabold mb-3" style={{ color: "var(--text)" }}>
              Set up your <span className="text-gradient">profile</span>
            </h1>
            <p style={{ color: "var(--text-muted)" }}>
              {step === "upload"
                ? "Bring a resume, paste a link, or start from scratch."
                : "Takes 3 minutes. Your first digest arrives tomorrow at 7 AM."}
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
