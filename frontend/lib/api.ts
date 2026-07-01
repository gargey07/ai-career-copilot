// Strips any trailing slash(es) so callers can safely do `${API_URL}/path`
// without risking a double slash — a trailing slash in the env var would
// otherwise turn every request into a 404 the backend never matches.
function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

export const API_URL = stripTrailingSlash(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
