import { API_URL } from "@/lib/api";

const SESSION_KEY = "acc:session_id";

// Anonymous per-browser id so funnel steps can be tied together before a
// user_id exists (created during onboarding, well before /confirm saves a
// user row). Not tied to any personal data.
function getSessionId(): string {
  try {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    return "unknown";
  }
}

const REF_KEY = "acc:ref";

// Invite/referral attribution: ?ref=<short id> arrives on the landing page
// or /signup, gets remembered for the browser session, and rides along on
// signup_started so the funnel can distinguish invited signups from
// organic ones. Measurement only — no rewards, no claims.
export function captureRef(): void {
  try {
    const ref = new URLSearchParams(window.location.search).get("ref");
    if (ref) sessionStorage.setItem(REF_KEY, ref.slice(0, 24));
  } catch {
    // sessionStorage unavailable — attribution just isn't recorded
  }
}

export function getRef(): string | null {
  try {
    return sessionStorage.getItem(REF_KEY);
  } catch {
    return null;
  }
}

// Fire-and-forget funnel logging (docs/PRODUCT_STRATEGY_BETA.md success
// metrics) — never awaited, never throws, never blocks the UI. keepalive
// lets the request survive an immediate page navigation (e.g. right after
// confirm succeeds and we redirect to /success).
export function trackEvent(event: string, opts?: { userId?: string; meta?: Record<string, unknown> }) {
  try {
    fetch(`${API_URL}/api/analytics/track`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event,
        session_id: getSessionId(),
        user_id: opts?.userId,
        meta: opts?.meta || {},
      }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // localStorage/fetch unavailable — analytics must never break the app
  }
}
