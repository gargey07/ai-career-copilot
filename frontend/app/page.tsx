"use client";

// ── Features Data ─────────────────────────────────────────────────────────────
const features = [
  {
    icon: "💼",
    title: "500+ Jobs Daily",
    desc: "Aggregated from LinkedIn, Indeed, Greenhouse, Adzuna & more — automatically.",
  },
  {
    icon: "✨",
    title: "AI Resume Optimizer",
    desc: "Gemini AI tailors your resume for each job with ATS keywords. Never generic.",
  },
  {
    icon: "📧",
    title: "Morning Digest",
    desc: "Wake up to your top matches with ready-to-send resumes & cover letters.",
  },
  {
    icon: "🎯",
    title: "Smart Matching",
    desc: "Vector AI ranks jobs by how well they match your profile — no wasted time.",
  },
];

// ── How It Works Steps ────────────────────────────────────────────────────────
const steps = [
  { num: "01", title: "Set Up Your Profile", desc: "Tell us your target role, experience, and paste your resume. Takes 3 minutes." },
  { num: "02", title: "We Collect Jobs", desc: "Every night our AI scans 5+ job boards so you don't have to." },
  { num: "03", title: "AI Matches & Optimizes", desc: "Your top matches get a fully tailored resume and cover letter." },
  { num: "04", title: "Apply in Minutes", desc: "Open your 7 AM email, pick a job, click apply. Done." },
];

export default function Home() {
  return (
    <main className="min-h-screen overflow-hidden" style={{ background: "#060614", color: "white", fontFamily: "Inter, sans-serif" }}>
      {/* Background gradient blobs */}
      <div style={{ position: "fixed", inset: 0, zIndex: -1, pointerEvents: "none" }}>
        <div style={{ position: "absolute", top: "-20%", left: "-10%", width: 600, height: 600, borderRadius: "50%", background: "rgba(59,130,246,0.15)", filter: "blur(120px)" }} />
        <div style={{ position: "absolute", bottom: "-20%", right: "-10%", width: 500, height: 500, borderRadius: "50%", background: "rgba(139,92,246,0.15)", filter: "blur(120px)" }} />
      </div>

      {/* ── Nav ── */}
      <nav className="flex items-center justify-between px-6 py-5 max-w-6xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold text-white" style={{ background: "linear-gradient(135deg, #3b82f6, #8b5cf6)" }}>
            AI
          </div>
          <span className="font-semibold text-white">Career Copilot</span>
        </div>
        <a
          href="/signup"
          id="nav-signup"
          className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all"
          style={{ background: "linear-gradient(135deg, #3b82f6, #8b5cf6)" }}
        >
          Join Free Beta →
        </a>
      </nav>

      {/* ── Hero ── */}
      <section className="text-center px-6 pt-20 pb-24 max-w-4xl mx-auto">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm mb-8" style={{ background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.3)", color: "#93c5fd" }}>
          <span className="w-2 h-2 rounded-full bg-blue-400 inline-block" style={{ animation: "pulse 2s infinite" }} />
          Beta — 5 spots remaining
        </div>

        <h1 className="text-5xl md:text-7xl font-extrabold leading-tight mb-6">
          Wake up to{" "}
          <span style={{ background: "linear-gradient(135deg, #60a5fa, #a78bfa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            perfect job matches
          </span>
          {" "}every morning.
        </h1>

        <p className="text-lg md:text-xl mb-12" style={{ color: "#9ca3af", maxWidth: 600, margin: "0 auto 3rem" }}>
          AI Career Copilot finds the best jobs for you, optimizes your resume with AI,
          and delivers everything to your inbox by 7 AM. Apply in under 10 minutes.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center" id="waitlist">
          <a
            href="/signup"
            id="hero-cta"
            className="inline-block px-8 py-4 rounded-xl font-bold text-white text-lg transition-all"
            style={{ background: "linear-gradient(135deg, #3b82f6, #8b5cf6)" }}
          >
            Join Free Beta — It&apos;s Free →
          </a>
          <a
            href="/dashboard?user_id=37c115cf-3cd5-4e06-be08-d9c60a1e489c"
            id="hero-dashboard"
            className="inline-block px-8 py-4 rounded-xl font-semibold text-white text-lg transition-all"
            style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
          >
            View Demo Dashboard
          </a>
        </div>
        <p className="text-sm mt-4" style={{ color: "#6b7280" }}>Free during beta. No credit card required.</p>
      </section>

      {/* ── Features ── */}
      <section className="px-6 py-20 max-w-6xl mx-auto">
        <h2 className="text-center text-3xl font-bold mb-12 text-white">
          Everything automated. Nothing manual.
        </h2>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-2xl p-6 transition-all"
              style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
            >
              <div className="text-3xl mb-4">{f.icon}</div>
              <h3 className="font-semibold text-white mb-2">{f.title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: "#9ca3af" }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How It Works ── */}
      <section className="px-6 py-20 max-w-4xl mx-auto">
        <h2 className="text-center text-3xl font-bold mb-12 text-white">How it works</h2>
        <div className="space-y-6">
          {steps.map((step) => (
            <div key={step.num} className="flex gap-6 items-start">
              <div
                className="flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-sm font-bold"
                style={{ background: "rgba(59,130,246,0.15)", border: "1px solid rgba(255,255,255,0.1)", color: "#93c5fd" }}
              >
                {step.num}
              </div>
              <div className="pt-1">
                <h3 className="font-semibold text-white mb-1">{step.title}</h3>
                <p className="text-sm" style={{ color: "#9ca3af" }}>{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer CTA ── */}
      <section className="text-center px-6 py-24">
        <h2 className="text-3xl md:text-4xl font-bold mb-4 text-white">
          Stop scrolling job boards.<br />
          <span style={{ background: "linear-gradient(135deg, #60a5fa, #a78bfa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            Start getting hired.
          </span>
        </h2>
        <p className="mb-8" style={{ color: "#9ca3af" }}>Free during beta. Join 5 early users.</p>
        <a
          href="/signup"
          className="inline-block px-8 py-4 rounded-xl font-semibold text-white text-lg transition-all"
          style={{ background: "linear-gradient(135deg, #3b82f6, #8b5cf6)" }}
        >
          Get Early Access →
        </a>
      </section>

      {/* ── Footer ── */}
      <footer className="px-6 py-8 text-center text-sm" style={{ borderTop: "1px solid rgba(255,255,255,0.08)", color: "#6b7280" }}>
        <p>
          Built by{" "}
          <a href="https://gargey-patel-portfolio.vercel.app" className="text-blue-400 hover:underline">
            Gargey Patel
          </a>{" "}
          · gargeypatel123@gmail.com
        </p>
      </footer>
    </main>
  );
}
