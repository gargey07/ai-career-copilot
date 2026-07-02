"use client";

import { useEffect } from "react";
import { API_URL } from "@/lib/api";

// Render's free tier spins the backend down after ~15 minutes idle, and a
// cold start takes ~50s. Fire a tiny /health ping the moment any page loads
// so the backend is waking up while the visitor is still reading — by the
// time they upload a resume or open the dashboard, it's usually warm.
// Renders nothing; failures are irrelevant (the ping IS the point).
export function WarmBackend() {
  useEffect(() => {
    fetch(`${API_URL}/health`, { cache: "no-store" }).catch(() => {});
  }, []);
  return null;
}
