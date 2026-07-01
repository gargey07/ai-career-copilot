import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AI Career Copilot — Wake up to tailored jobs every morning",
  description:
    "AI Career Copilot automatically discovers relevant jobs, optimizes your resume with AI, and delivers a personalized morning digest—so you can apply in under 10 minutes.",
  keywords: ["job search", "AI resume", "career automation", "ATS optimization"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className={`${inter.className} antialiased`} style={{ background: "#F8FAFC", color: "#0F2F3A" }}>
        {children}
      </body>
    </html>
  );
}
