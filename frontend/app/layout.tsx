import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

const SITE_URL = "https://ai-career-copilot-taupe-five.vercel.app";
const TITLE = "AI Career Copilot — Wake up to tailored jobs every morning";
const DESCRIPTION =
  "AI Career Copilot automatically discovers relevant jobs, tailors your resume with AI, and has your best matches ready every morning—so you can apply in under 10 minutes.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  keywords: ["job search", "AI resume", "career automation", "ATS optimization"],
  // Shared links (WhatsApp/LinkedIn/Twitter) unfurl with a real preview —
  // this is where beta invites will mostly travel.
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: "AI Career Copilot",
    type: "website",
    locale: "en_IN",
  },
  twitter: {
    card: "summary",
    title: TITLE,
    description: DESCRIPTION,
  },
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
