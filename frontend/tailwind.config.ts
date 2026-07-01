import type { Config } from "tailwindcss";

// Design tokens — see docs/design-system.md (source of truth).
const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        bg: "#F8FAFC",
        surface: "#FFFFFF",
        "surface-muted": "#F1F5F9",
        border: "#E5E7EB",
        ink: {
          DEFAULT: "#0F2F3A", // primary text (dark teal)
          muted: "#64748B",
        },
        teal: {
          DEFAULT: "#0F2F3A",
          600: "#0F9D8C", // success / accent teal-green
        },
        primary: {
          DEFAULT: "#F59E0B",
          hover: "#D97706",
        },
        accent: "#F97316",
        coral: "#EF4444",
        success: "#0F9D8C",
      },
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "16px",
        xl: "24px",
      },
      boxShadow: {
        e1: "0 1px 3px rgba(15,47,58,.06)",
        e2: "0 4px 12px rgba(15,47,58,.08)",
        e3: "0 12px 32px rgba(15,47,58,.12)",
      },
      animation: {
        "fade-in": "fade-in 0.5s ease-out both",
        "slide-up": "slide-up 0.4s ease-out both",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-up": {
          "0%": { transform: "translateY(16px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
