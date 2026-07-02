import { Briefcase, Sparkles, Mail, Target, ArrowRight } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { NavCta } from "@/components/NavCta";
import { HeroCtas } from "@/components/HeroCtas";
import { WarmBackend } from "@/components/WarmBackend";
import { BRAND_NAME } from "@/lib/brand";
import type { LucideIcon } from "lucide-react";

// ── Features Data ─────────────────────────────────────────────────────────────
// Trust rule (docs/PRODUCT_STRATEGY_BETA.md): no invented numbers, no internal
// implementation names, no promises about features that aren't live yet.
const features: { icon: LucideIcon; title: string; desc: string }[] = [
  { icon: Briefcase, title: "Fresh Jobs Daily", desc: "New openings collected from multiple job boards every day — automatically." },
  { icon: Sparkles, title: "AI Resume Tailoring", desc: "Your resume, rewritten for each job with ATS keywords. Never invented, never generic." },
  { icon: Mail, title: "Morning Briefing", desc: "Start each day with your top matches, ranked and ready on your dashboard." },
  { icon: Target, title: "Smart Matching", desc: "AI ranks every job by how well it fits your profile — no wasted time." },
];

const steps = [
  { num: "01", title: "Set Up Your Profile", desc: "Bring your resume or start from scratch. Takes 3 minutes." },
  { num: "02", title: "We Collect Jobs", desc: "We scan multiple job boards every day so you don't have to." },
  { num: "03", title: "AI Matches & Tailors", desc: "Your top matches are ranked, each with a resume tailored to the role." },
  { num: "04", title: "Apply in Minutes", desc: "Open your morning briefing, pick a job, click apply. Done." },
];

export default function Home() {
  return (
    <main className="min-h-screen" style={{ background: "var(--bg)", color: "var(--text)" }}>
      {/* ── Nav ── */}
      <WarmBackend />
      <nav className="flex items-center justify-between px-6 py-5 max-w-6xl mx-auto">
        <BrandMark />
        <NavCta />
      </nav>

      {/* ── Hero ── */}
      <section className="text-center px-6 pt-20 pb-24 max-w-4xl mx-auto">
        <div
          className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm mb-8"
          style={{ background: "#FEF3C7", border: "1px solid #FDE68A", color: "#B45309" }}
        >
          <span className="w-2 h-2 rounded-full inline-block" style={{ background: "var(--primary)" }} />
          Free Beta — now open
        </div>

        <h1 className="text-5xl md:text-7xl font-extrabold leading-tight mb-6" style={{ color: "var(--text)" }}>
          Wake up to <span className="text-gradient">perfect job matches</span> every morning.
        </h1>

        <p className="text-lg md:text-xl mb-12 mx-auto" style={{ color: "var(--text-muted)", maxWidth: 600 }}>
          {BRAND_NAME} finds the best jobs for you, tailors your resume with AI, and has everything
          ready on your dashboard each morning. Apply in under 10 minutes.
        </p>

        <HeroCtas />
      </section>

      {/* ── Features ── */}
      <section className="px-6 py-20 max-w-6xl mx-auto">
        <h2 className="text-center text-3xl font-bold mb-12" style={{ color: "var(--text)" }}>
          Everything automated. Nothing manual.
        </h2>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-lg p-6 transition hover:shadow-e2"
              style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-e1)" }}
            >
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-md" style={{ background: "#FEF3C7" }}>
                <f.icon size={22} strokeWidth={1.75} style={{ color: "var(--primary)" }} />
              </div>
              <h3 className="font-semibold mb-2" style={{ color: "var(--text)" }}>{f.title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How It Works ── */}
      <section className="px-6 py-20 max-w-4xl mx-auto">
        <h2 className="text-center text-3xl font-bold mb-12" style={{ color: "var(--text)" }}>How it works</h2>
        <div className="space-y-6">
          {steps.map((step) => (
            <div key={step.num} className="flex gap-6 items-start">
              <div
                className="flex-shrink-0 w-12 h-12 rounded-md flex items-center justify-center text-sm font-bold"
                style={{ background: "#FEF3C7", color: "#B45309" }}
              >
                {step.num}
              </div>
              <div className="pt-1">
                <h3 className="font-semibold mb-1" style={{ color: "var(--text)" }}>{step.title}</h3>
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer CTA ── */}
      <section className="text-center px-6 py-24">
        <h2 className="text-3xl md:text-4xl font-bold mb-4" style={{ color: "var(--text)" }}>
          Stop scrolling job boards.<br />
          <span className="text-gradient">Start getting hired.</span>
        </h2>
        <p className="mb-8" style={{ color: "var(--text-muted)" }}>Free during beta. No credit card required.</p>
        <a
          href="/signup"
          className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-md font-semibold text-white text-lg transition hover:opacity-90"
          style={{ background: "var(--primary)", boxShadow: "var(--shadow-e1)" }}
        >
          Get Early Access
          <ArrowRight size={18} strokeWidth={2} />
        </a>
      </section>

      {/* ── Footer ── */}
      <footer className="px-6 py-8 text-center text-sm" style={{ borderTop: "1px solid var(--border)", color: "var(--text-muted)" }}>
        <p>
          Built by{" "}
          <a href="https://gargey-patel-portfolio.vercel.app" className="hover:underline" style={{ color: "var(--primary)" }}>
            Gargey Patel
          </a>{" "}
          · gargeypatel123@gmail.com
        </p>
      </footer>
    </main>
  );
}
