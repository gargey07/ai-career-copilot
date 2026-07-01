"use client";

import { useRef, useState } from "react";
import { UploadCloud, Link as LinkIcon, PencilLine, AlertTriangle, FileText } from "lucide-react";
import { API_URL } from "@/lib/api";
import { emptyProfile, profileFromParsed, type Profile } from "@/lib/profile";
import { SectionCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Skeleton } from "@/components/ui/Skeleton";
import { Stepper, type Step } from "@/components/ui/Stepper";

interface UploadStepProps {
  onReady: (profile: Profile, resumeFilePath: string | null) => void;
}

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const POLL_INTERVAL_MS = 2000;

type Mode = "choose" | "url" | "loading";

const PARSING_STEPS: Step[] = [
  { label: "Uploaded", state: "done" },
  { label: "AI Parsing", state: "active" },
  { label: "Verified", state: "pending" },
  { label: "Ready", state: "pending" },
];

export default function UploadStep({ onReady }: UploadStepProps) {
  const [mode, setMode] = useState<Mode>("choose");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [testResult, setTestResult] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const testConnection = async () => {
    setTestResult("Testing GET…");
    try {
      const res = await fetch(`${API_URL}/health`);
      const text = await res.text();
      setTestResult(`GET: ${res.status} ${res.ok ? "OK" : ""} — ${text}`);
    } catch (e: any) {
      setTestResult(`GET FAILED: ${e.message || e}`);
      return;
    }
    setTestResult((prev) => prev + " | Testing POST…");
    try {
      const res = await fetch(`${API_URL}/api/resumes/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const text = await res.text();
      setTestResult((prev) => prev.replace(" | Testing POST…", "") + ` | POST: ${res.status} — ${text.slice(0, 150)}`);
    } catch (e: any) {
      setTestResult((prev) => prev.replace(" | Testing POST…", "") + ` | POST FAILED: ${e.message || e}`);
    }
  };

  const stopPolling = () => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
    pollTimer.current = null;
  };

  const pollStatus = (jobId: string) => {
    pollTimer.current = setTimeout(async () => {
      try {
        const res = await fetch(`${API_URL}/api/resumes/parse-status/${jobId}`);
        if (!res.ok) throw new Error("Lost track of that upload. Please try again.");
        const data = await res.json();
        if (data.status === "done") {
          onReady(profileFromParsed(data.result || {}), data.file_path || null);
        } else if (data.status === "failed") {
          setError(data.error_message || "Couldn't parse that resume.");
          setMode("choose");
        } else {
          pollStatus(jobId);
        }
      } catch (e: any) {
        setError(e.message || "Something went wrong checking your upload.");
        setMode("choose");
      }
    }, POLL_INTERVAL_MS);
  };

  const validateFile = (file: File): string | null => {
    const ext = file.name.toLowerCase().split(".").pop();
    if (ext !== "pdf" && ext !== "docx") return "Please upload a .pdf or .docx file.";
    if (file.size > MAX_FILE_BYTES) return "File is too large — max 5MB.";
    return null;
  };

  const uploadFile = async (file: File) => {
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError("");
    setMode("loading");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/api/resumes/upload`, { method: "POST", body: formData });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Upload failed. Please try again.");
      }
      const { job_id } = await res.json();
      pollStatus(job_id);
    } catch (e: any) {
      setError(e.message || "Upload failed. Please try again.");
      setMode("choose");
    }
  };

  const submitUrl = async () => {
    if (!url.trim()) {
      setError("Paste a link to your resume first.");
      return;
    }
    setError("");
    setMode("loading");
    try {
      const res = await fetch(`${API_URL}/api/resumes/upload-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Couldn't fetch that URL. Please try again.");
      }
      const { job_id } = await res.json();
      pollStatus(job_id);
    } catch (e: any) {
      setError(e.message || "Couldn't fetch that URL. Please try again.");
      setMode("choose");
    }
  };

  // ── Loading state: stepper + skeleton of the review form ──────────────────
  if (mode === "loading") {
    return (
      <SectionCard>
        <div className="max-w-md mx-auto mb-8">
          <Stepper steps={PARSING_STEPS} />
        </div>
        <div className="text-center mb-8">
          <h2 className="text-lg font-semibold" style={{ color: "var(--text)" }}>Reading your resume…</h2>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>This usually takes 5–15 seconds.</p>
        </div>
        <div className="space-y-3">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-11 w-full" />
          <Skeleton className="h-11 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
        <div className="mt-6 text-center">
          <button
            type="button"
            onClick={() => {
              stopPolling();
              setMode("choose");
            }}
            className="text-sm transition hover:opacity-70"
            style={{ color: "var(--text-muted)" }}
          >
            Cancel
          </button>
        </div>
      </SectionCard>
    );
  }

  return (
    <SectionCard icon={FileText} title="Bring your resume">
      <p className="text-sm -mt-3 mb-5" style={{ color: "var(--text-muted)" }}>
        We&apos;ll read it and pre-fill everything below — you just double-check it.
      </p>

      {mode === "choose" && (
        <div className="space-y-5">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const file = e.dataTransfer.files?.[0];
              if (file) uploadFile(file);
            }}
            onClick={() => fileInputRef.current?.click()}
            className="rounded-lg p-10 text-center cursor-pointer transition border-2 border-dashed"
            style={{
              borderColor: dragOver ? "var(--primary)" : "var(--border)",
              background: dragOver ? "#FEF9EF" : "transparent",
            }}
          >
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "var(--surface-muted)" }}>
              <UploadCloud size={24} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
            </div>
            <p className="font-medium" style={{ color: "var(--text)" }}>Drag &amp; drop your resume here</p>
            <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>or click to browse — .pdf or .docx, max 5MB</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) uploadFile(file);
              }}
            />
          </div>

          <div className="flex items-center gap-3 text-xs" style={{ color: "var(--text-muted)" }}>
            <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
            or
            <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <Button variant="secondary" className="flex-1" onClick={() => setMode("url")}>
              <LinkIcon size={16} strokeWidth={1.75} />
              Paste a resume URL
            </Button>
            <Button variant="secondary" className="flex-1" onClick={() => onReady(emptyProfile(), null)}>
              <PencilLine size={16} strokeWidth={1.75} />
              Start from scratch
            </Button>
          </div>
        </div>
      )}

      {mode === "url" && (
        <div className="space-y-4">
          <Field label="Link to your resume" helper="Google Drive, Dropbox, or a personal site.">
            <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
          </Field>
          <div className="flex gap-3">
            <Button variant="primary" onClick={submitUrl}>Continue</Button>
            <Button
              variant="ghost"
              onClick={() => {
                setMode("choose");
                setError("");
              }}
            >
              Back
            </Button>
          </div>
        </div>
      )}

      {error && (
        <div className="mt-5 rounded-md px-4 py-3 text-sm flex items-start gap-2" style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "var(--coral)" }}>
          <AlertTriangle size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" />
          <span>
            {error}{" "}
            <button type="button" onClick={() => onReady(emptyProfile(), null)} className="underline font-medium hover:opacity-70">
              Fill in manually instead
            </button>
          </span>
        </div>
      )}

      {/* Temporary debug tools — remove once uploads are confirmed stable in prod. */}
      <div className="mt-6 pt-4 border-t space-y-2" style={{ borderColor: "var(--border)" }}>
        <button type="button" onClick={testConnection} className="text-xs underline transition hover:opacity-70" style={{ color: "var(--text-muted)" }}>
          Test backend connection
        </button>
        <p className="text-xs break-all" style={{ color: "#94A3B8" }}>API_URL: {API_URL}</p>
        {testResult && <p className="text-xs break-all" style={{ color: "var(--text-muted)" }}>Result: {testResult}</p>}
      </div>
    </SectionCard>
  );
}
