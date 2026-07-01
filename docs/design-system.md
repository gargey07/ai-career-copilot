# AI Career Copilot — Design System

> **Source of truth for all UI.** Read this before writing or changing any interface code.
> When a value here and the code disagree, this document wins — fix the code.

Implemented in `frontend/app/globals.css` (CSS custom properties + utilities) and
`frontend/tailwind.config.ts` (Tailwind tokens). Reusable primitives live in
`frontend/components/ui/`.

---

## 1. Design philosophy

The product should feel like **Linear, Notion, and Arc** — calm, fast, and precise.

- Generous whitespace; let content breathe.
- Soft shadows, not hard borders, to separate surfaces.
- Rounded corners everywhere.
- Smooth, subtle motion — never bouncy or attention-seeking.
- **Zero clutter. Exactly one primary action per screen.**
- Fast: skeletons over spinners, optimistic where safe.

**Not** this: Material Design, Bootstrap, or a dense admin-panel look.

---

## 2. Colors

Light theme. Brand palette: dark teal + warm orange/coral.

| Token | Hex | Use |
| --- | --- | --- |
| `--bg` | `#F8FAFC` | Page background |
| `--surface` | `#FFFFFF` | Cards, inputs, elevated surfaces |
| `--surface-muted` | `#F1F5F9` | Subtle fills (skeletons, hover) |
| `--border` | `#E5E7EB` | Hairline borders |
| `--text` | `#0F2F3A` | Headings, primary text (dark teal) |
| `--text-muted` | `#64748B` | Labels, secondary text |
| `--primary` | `#F59E0B` | Primary buttons, active states, focus ring |
| `--primary-hover` | `#D97706` | Primary hover |
| `--accent` | `#F97316` | Secondary accent |
| `--coral` / `--danger` | `#EF4444` | Errors, destructive, highlights |
| `--success` | `#0F9D8C` | Success states (teal-green) |
| `--warning` | `#F59E0B` | "Low confidence" / attention nudges |

Rules:
- Text on `--primary` is white; text on `--surface` is `--text`.
- Never use the old blue `#3b82f6` / purple `#8b5cf6`. They are banned.
- Selected chips: amber tint — bg `#FEF3C7`, border `--primary`, text `#B45309`.
- Emphasis heading word uses the orange→coral gradient (`.text-gradient`); everything
  else is solid `--text`.

---

## 3. Typography

Font: **Inter** (already loaded).

| Role | Size / weight | Notes |
| --- | --- | --- |
| Display (hero) | 44–64px / 800 | Landing only |
| H1 (page title) | 32–36px / 700 | One per screen |
| H2 (section) | 18–20px / 600 | Card headers |
| Body | 15–16px / 400 | `--text` |
| Label | 13–14px / 500 | `--text-muted`, above every field |
| Caption / helper | 12–13px / 400 | `--text-muted` |

Line-height 1.5 for body, 1.2 for headings. Never rely on placeholder text as a label.

---

## 4. Spacing

4px base scale: `4, 8, 12, 16, 20, 24, 32, 40, 48, 64`. Card padding `24–32px`.
Gap between form fields `16px`; between sections `24–32px`.

---

## 5. Radius

| Token | px | Use |
| --- | --- | --- |
| sm | 8 | Chips, small controls |
| md | 12 | Inputs, buttons |
| lg | 16 | Cards |
| xl | 24 | Large panels, modals |
| full | 9999 | Pills, avatars, dots |

---

## 6. Elevation (shadows on white)

Soft, low-opacity teal-tinted shadows — no hard black.

| Level | Value | Use |
| --- | --- | --- |
| e1 | `0 1px 3px rgba(15,47,58,.06)` | Resting cards |
| e2 | `0 4px 12px rgba(15,47,58,.08)` | Hover, dropdowns |
| e3 | `0 12px 32px rgba(15,47,58,.12)` | Modals, popovers |

---

## 7. Motion

Durations: 150ms (micro — hovers), 250ms (enter), 400ms (page-level). Easing:
`ease-out` for enters, `ease-in-out` for loops. Respect `prefers-reduced-motion`.
Keep the existing `fade-in` / `slide-up` keyframes; drop `pulse-glow` (too flashy).

---

## 8. Iconography

**Never use emojis in the UI. Ever.**

- **Lucide React only** (`lucide-react`, already installed).
- Default size **20px**, stroke **1.5–2px**.
- Semantic color: inherit `--text-muted` by default; `--primary` for active/interactive;
  `--danger` for destructive.
- Icons **support** a text label — they do not replace it.

Canonical mappings: User (basic info) · FileText (summary/resume) · Briefcase (experience/
jobs) · GraduationCap (education) · Target (roles/skills/match) · Link/Linkedin/Github/
Globe (links) · Upload/UploadCloud (upload) · Search (search) · Trash2 (remove) ·
AlertTriangle (error) · CheckCircle (success) · Clock (empty/pending) · Sparkles (AI) ·
Mail (digest) · Sun (greeting). Category tiles: Palette, MonitorSmartphone, Server,
Layers, ClipboardList, Brain.

---

## 9. Forms

- Every field uses the `Field` primitive: **persistent label above the control** +
  optional helper/error below. Placeholders are examples, never the only label.
- Inputs: `--surface` bg, 1px `--border`, radius md, 12px vertical padding.
- Focus: 2px `--primary` ring, no default outline.
- Textareas size to their content role (summary ≥6 rows, bullets ≥5 rows).
- Multi-select: `SearchSelect` (type-ahead + chips + "add custom"); always allow a custom
  value.

---

## 10. Buttons

One primary style; everything else recedes.

| Variant | Look | Use |
| --- | --- | --- |
| Primary | `--primary` bg, white text, e1 shadow | The single main action |
| Secondary | `--surface` bg, `--border`, `--text` | Alternate actions |
| Ghost | transparent, `--text-muted`, hover fill | Tertiary / cancel |
| Danger | `--danger` text/border | Destructive |

Radius md, 500 weight, disabled = 50% opacity + not-allowed. One primary per screen.

---

## 11. Cards

White `--surface`, 1px `--border`, radius lg, e1 shadow, 24–32px padding. Optional header
= Lucide icon (`--primary`) + H2 title. Use `Card` / `SectionCard` primitives.

---

## 12. State rules — every screen has all four

Never show a raw spinner or a blank screen.

- **Loading** → **Skeleton** shimmer blocks matching the final layout. No spinners.
- **Empty** → `EmptyState`: icon + headline + one sentence + optional single action.
  e.g. *"No jobs yet — we'll notify you tomorrow morning."*
- **Error** → inline card, `--danger` accent, plain-language message + retry/next step.
- **Success** → the populated view, or a confirmation with a clear next action.

Long async flows (e.g. resume parsing) show progress via `Stepper`
(Uploaded → AI Parsed → Verified → Ready), not just a spinner.

---

## 13. Accessibility

- Text contrast ≥ 4.5:1 (`--text`/`--text-muted` on `--bg`/`--surface` all pass).
- Visible focus ring on every interactive element.
- Hit targets ≥ 40px. Icon-only buttons need `aria-label`.
- Motion respects `prefers-reduced-motion`.
