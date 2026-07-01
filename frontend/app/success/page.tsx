"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

function SuccessContent() {
  const params = useSearchParams();
  const name   = params.get("name") || "Friend";
  const id     = params.get("id") || "";

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6">
      {/* Background */}
      <div className="fixed inset-0 -z-10 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full bg-blue-600/10 blur-[120px]" />
      </div>

      <div className="max-w-lg w-full text-center animate-fade-in space-y-8">
        {/* Celebration icon */}
        <div className="relative inline-block animate-float">
          <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-5xl mx-auto shadow-2xl">
            🎉
          </div>
          <div className="absolute -top-2 -right-2 w-8 h-8 rounded-full bg-green-500 flex items-center justify-center text-lg">✓</div>
        </div>

        {/* Heading */}
        <div>
          <h1 className="text-4xl md:text-5xl font-extrabold mb-3">
            You&apos;re in,{" "}
            <span className="text-gradient">{name.split(" ")[0]}!</span>
          </h1>
          <p className="text-gray-400 text-lg">
            Your profile is live. The AI is already learning your preferences.
          </p>
        </div>

        {/* What happens next */}
        <div className="glass rounded-2xl p-8 text-left space-y-5">
          <h2 className="font-semibold text-white text-lg mb-4">⏰ What happens next</h2>

          {[
            { time: "Tonight 2 AM",  icon: "🔍", desc: "Our AI scans 5+ job boards and finds fresh UI/UX roles" },
            { time: "Tonight 6 AM",  icon: "🤖", desc: "Gemini matches the best jobs to your exact profile" },
            { time: "Tonight 6:30 AM", icon: "📝", desc: "AI rewrites your resume tailored for each job" },
            { time: "Tomorrow 7 AM", icon: "📧", desc: "Digest lands in your inbox — ready to apply in 2 minutes" },
          ].map((item) => (
            <div key={item.time} className="flex items-start gap-4">
              <div className="flex-shrink-0 text-2xl">{item.icon}</div>
              <div>
                <div className="text-sm font-semibold text-blue-300">{item.time}</div>
                <div className="text-sm text-gray-400">{item.desc}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Dashboard link */}
        {id && (
          <div className="glass rounded-2xl p-6 text-center">
            <p className="text-sm text-gray-400 mb-4">
              Bookmark your personal dashboard — check your matches anytime:
            </p>
            <a
              href={`/dashboard?user_id=${id}`}
              id="success-dashboard-link"
              className="inline-block px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 font-semibold text-white transition-all text-sm"
            >
              Open My Dashboard →
            </a>
          </div>
        )}

        {/* Footer */}
        <p className="text-sm text-gray-600">
          Email us at{" "}
          <a href="mailto:gargeypatel123@gmail.com" className="text-blue-400 hover:underline">
            gargeypatel123@gmail.com
          </a>{" "}
          if you have questions.
        </p>
      </div>
    </main>
  );
}

export default function SuccessPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-gray-400">Loading...</div>}>
      <SuccessContent />
    </Suspense>
  );
}
