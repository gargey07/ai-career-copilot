import { BRAND_NAME } from "@/lib/brand";

// Logo mark + wordmark. Single place the brand name/logo is rendered in nav.
export function BrandMark({ href = "/" }: { href?: string }) {
  return (
    <a href={href} className="flex items-center gap-2.5 group">
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold text-white shrink-0"
        style={{ background: "linear-gradient(135deg, #F59E0B, #EF4444)" }}
        aria-hidden="true"
      >
        AI
      </div>
      <span className="font-semibold transition-colors group-hover:opacity-80" style={{ color: "var(--text)" }}>
        {BRAND_NAME}
      </span>
    </a>
  );
}
