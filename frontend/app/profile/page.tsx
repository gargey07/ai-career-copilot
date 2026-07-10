"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import ProfileEditor from "../signup/ProfileEditor";
import { profileFromParsed, type Profile } from "@/lib/profile";
import { API_URL } from "@/lib/api";
import { BrandMark } from "@/components/BrandMark";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { getStoredProfile, saveStoredProfile } from "@/lib/localProfile";

// Same format as the dashboard: the signed token is "{user_id}.{sig}".
function userIdFromToken(token: string): string | null {
  const i = token.lastIndexOf(".");
  return i > 0 ? token.slice(0, i) : null;
}

function ProfileEditInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("t") || getStoredProfile()?.token || "";
  const userId = userIdFromToken(token);

  const [profile, setProfile] = useState<Profile | null>(null);
  const [resumeFilePath, setResumeFilePath] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token || !userId) {
      setError("This link is invalid — open your dashboard and tap Edit profile again.");
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/users/${userId}/profile?t=${encodeURIComponent(token)}`);
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || "Couldn't load your profile.");
        }
        const data = await res.json();
        setResumeFilePath(data.resume_file_path || null);
        setProfile(profileFromParsed(data));
      } catch (e: any) {
        setError(e.message || "Couldn't load your profile.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Saving goes through the same /resumes/confirm upsert as signup — the
  // editor handles the POST itself and hands back the (fresh) token.
  const handleConfirmed = (id: string, name: string, dashboardToken: string) => {
    saveStoredProfile({ id, name, token: dashboardToken || token });
    router.push(`/dashboard?t=${encodeURIComponent(dashboardToken || token)}`);
  };

  return (
    <main className="min-h-screen" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <nav className="flex items-center justify-between px-6 py-5 max-w-4xl mx-auto">
        <BrandMark />
        <a
          href={token ? `/dashboard?t=${encodeURIComponent(token)}` : "/dashboard"}
          className="text-sm font-medium hover:underline"
          style={{ color: "var(--text-muted)" }}
        >
          Back to dashboard
        </a>
      </nav>

      <div className="px-6 pb-20 max-w-4xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Edit your profile</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            The more complete this is, the better your matches and tailored resumes get.
          </p>
        </div>

        {error ? (
          <Card className="p-6">
            <p className="flex items-start gap-2 text-sm" style={{ color: "var(--coral)" }}>
              <AlertTriangle size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" />
              {error}
            </p>
          </Card>
        ) : profile ? (
          <ProfileEditor initialProfile={profile} resumeFilePath={resumeFilePath} onConfirmed={handleConfirmed} />
        ) : (
          <div className="space-y-4">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-64 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        )}
      </div>
    </main>
  );
}

export default function ProfileEditPage() {
  return (
    <Suspense fallback={null}>
      <ProfileEditInner />
    </Suspense>
  );
}
