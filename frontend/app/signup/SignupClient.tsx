"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import UploadStep from "./UploadStep";
import ReviewStep from "./ReviewStep";
import { emptyProfile, type Profile } from "@/lib/profile";

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
    <main className="min-h-screen flex flex-col" style={{ background: "#060614", color: "white" }}>
      {/* Background */}
      <div className="fixed inset-0 -z-10 pointer-events-none">
        <div className="absolute top-[-10%] left-[-5%]  w-[500px] h-[500px] rounded-full bg-blue-600/15   blur-[100px]" />
        <div className="absolute bottom-[-10%] right-[-5%] w-[400px] h-[400px] rounded-full bg-purple-600/15 blur-[100px]" />
      </div>

      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-5 max-w-4xl mx-auto w-full">
        <a href="/" className="flex items-center gap-2 group">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold text-white" style={{ background: "linear-gradient(135deg,#3b82f6,#8b5cf6)" }}>
            AI
          </div>
          <span className="font-semibold text-white group-hover:text-blue-300 transition-colors">Career Copilot</span>
        </a>
        <span className="text-sm text-gray-500">Free Beta — No credit card</span>
      </nav>

      {/* Form */}
      <div className="flex-1 flex items-start justify-center px-4 py-10">
        <div className="w-full max-w-2xl">
          <div className="text-center mb-10">
            <h1 className="text-4xl font-extrabold mb-3">
              Set up your{" "}
              <span style={{ background: "linear-gradient(135deg,#60a5fa,#a78bfa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                profile
              </span>
            </h1>
            <p className="text-gray-400">
              {step === "upload"
                ? "Bring a resume, paste a link, or start from scratch."
                : "Takes 3 minutes. Your first digest arrives tomorrow at 7 AM."}
            </p>
          </div>

          {step === "upload" && <UploadStep onReady={handleUploadReady} />}
          {step === "review" && (
            <ReviewStep initialProfile={profile} resumeFilePath={resumeFilePath} onConfirmed={handleConfirmed} />
          )}
        </div>
      </div>
    </main>
  );
}
