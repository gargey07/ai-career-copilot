"use client";

import { useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import { emptyProfile, profileFromParsed, type Profile } from "@/lib/profile";

interface UploadStepProps {
  onReady: (profile: Profile, resumeFilePath: string | null) => void;
}

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const POLL_INTERVAL_MS = 2000;

type Mode = "choose" | "url" | "loading";

export default function UploadStep({ onReady }: UploadStepProps) {
  const [mode, setMode] = useState<Mode>("choose");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [testResult, setTestResult] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const testConnection = async () => {
    setTestResult("Testing…");
    try {
      const res = await fetch(`${API_URL}/health`);
      const text = await res.text();
      setTestResult(`${res.status} ${res.ok ? "OK" : ""} — ${text}`);
    } catch (e: any) {
      setTestResult(`FAILED: ${e.message || e}`);
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
          pollStatus(jobId); // still pending/processing
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

  const cardStyle = { background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" };

  if (mode === "loading") {
    return (
      <div className="rounded-2xl p-12 text-center space-y-4" style={cardStyle}>
        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 mx-auto animate-spin" />
        <h2 className="font-semibold text-white text-lg">Reading your resume…</h2>
        <p className="text-sm text-gray-500">Usually takes 5-15 seconds.</p>
        <button
          type="button"
          onClick={() => {
            stopPolling();
            setMode("choose");
          }}
          className="text-sm text-gray-500 hover:text-white transition-colors"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl p-8 space-y-6" style={cardStyle}>
        <div>
          <h2 className="font-semibold text-white text-lg">📄 Bring your resume</h2>
          <p className="text-sm text-gray-500 mt-1">
            We&apos;ll read it and pre-fill everything below — you just double-check it.
          </p>
        </div>

        {mode === "choose" && (
          <>
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
              className={`rounded-xl p-10 text-center cursor-pointer transition-all border-2 border-dashed ${
                dragOver ? "border-blue-500 bg-blue-500/5" : "border-white/10 hover:border-white/20"
              }`}
            >
              <div className="text-3xl mb-3">⬆️</div>
              <p className="text-white font-medium">Drag & drop your resume here</p>
              <p className="text-sm text-gray-500 mt-1">or click to browse — .pdf or .docx, max 5MB</p>
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

            <div className="flex items-center gap-3 text-xs text-gray-600">
              <div className="flex-1 h-px bg-white/10" />
              or
              <div className="flex-1 h-px bg-white/10" />
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                onClick={() => setMode("url")}
                className="flex-1 px-4 py-3 rounded-xl text-sm font-medium border border-white/10 text-gray-300 hover:border-white/20 hover:text-white transition-all"
              >
                🔗 Paste a resume URL
              </button>
              <button
                type="button"
                onClick={() => onReady(emptyProfile(), null)}
                className="flex-1 px-4 py-3 rounded-xl text-sm font-medium border border-white/10 text-gray-300 hover:border-white/20 hover:text-white transition-all"
              >
                ✍️ Start from scratch
              </button>
            </div>
          </>
        )}

        {mode === "url" && (
          <div className="space-y-3">
            <label className="block text-sm text-gray-400">Link to your resume (Google Drive, Dropbox, personal site…)</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://..."
              className="w-full px-4 py-3 rounded-xl text-white placeholder-gray-600 transition"
              style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
            />
            <div className="flex gap-3">
              <button
                type="button"
                onClick={submitUrl}
                className="px-6 py-3 rounded-xl text-sm font-semibold text-white transition-all"
                style={{ background: "linear-gradient(135deg,#3b82f6,#8b5cf6)" }}
              >
                Continue
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode("choose");
                  setError("");
                }}
                className="px-6 py-3 rounded-xl text-sm text-gray-400 hover:text-white transition-colors"
              >
                Back
              </button>
            </div>
          </div>
        )}

        {error && (
          <div
            className="rounded-xl px-4 py-3 text-red-400 text-sm"
            style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)" }}
          >
            ⚠️ {error}
            {" "}
            <button type="button" onClick={() => onReady(emptyProfile(), null)} className="underline hover:text-red-300">
              Fill in manually instead
            </button>
          </div>
        )}

        {/* Temporary debug tools — remove once uploads are confirmed working */}
        <div className="pt-2 border-t border-white/5 space-y-2">
          <button type="button" onClick={testConnection} className="text-xs underline text-gray-500 hover:text-gray-300">
            Test backend connection
          </button>
          <p className="text-xs text-gray-700 break-all">API_URL: {API_URL}</p>
          {testResult && <p className="text-xs text-gray-400 break-all">Result: {testResult}</p>}
        </div>
      </div>
    </div>
  );
}
