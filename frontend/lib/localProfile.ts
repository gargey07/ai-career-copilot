// Remembers who this browser belongs to after they confirm their profile,
// so returning visitors get routed to their dashboard instead of signup.
// This is convenience, not auth — the dashboard is still a UUID-link model.

const STORAGE_KEY = "acc:profile";

export interface StoredProfile {
  id: string;
  name: string;
}

export function saveStoredProfile(profile: StoredProfile): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
  } catch {
    // Storage may be unavailable (private mode, blocked) — routing just
    // falls back to the signup-first experience.
  }
}

export function getStoredProfile(): StoredProfile | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.id === "string" && parsed.id) {
      return { id: parsed.id, name: typeof parsed.name === "string" ? parsed.name : "" };
    }
  } catch {
    // fall through
  }
  return null;
}

export function clearStoredProfile(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
