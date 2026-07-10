"use client";

import { useEffect } from "react";
import { captureRef } from "@/lib/analytics";

// Invisible: remembers an invite ref (?ref=...) for this browser session so
// signup_started can carry it (lib/analytics.ts). Lives in a client
// component because the landing page itself is a server component.
export function RefCapture() {
  useEffect(() => {
    captureRef();
  }, []);
  return null;
}
