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
