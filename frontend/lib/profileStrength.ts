import type { Profile } from "@/lib/profile";

// Profile Strength — show progress, not errors (docs/PRODUCT_STRATEGY_BETA.md).
// Each item carries a weight and a WHY sentence (the encouragement copy from
// the strategy doc). Nothing here is "required"; the meter motivates.
//
// NOTE: the backend mirrors these weights in api/routes/users.py for the
// dashboard's server-computed strength — keep the two lists in sync.

export interface StrengthItem {
  key: string;
  label: string;
  weight: number;
  why: string;
  done: boolean;
}

export interface ProfileStrengthResult {
  percent: number;
  completed: StrengthItem[];
  pending: StrengthItem[];
}

const has = (s: string | undefined | null) => !!s && s.trim().length > 0;

export function computeProfileStrength(profile: Profile, hasResume: boolean): ProfileStrengthResult {
  const items: StrengthItem[] = [
    {
      key: "resume",
      label: "Resume",
      weight: 20,
      why: "Uploading a resume allows AI to tailor every application automatically.",
      done: hasResume,
    },
    {
      key: "summary",
      label: "Summary",
      weight: 10,
      why: "A short summary helps recruiters understand you at a glance.",
      done: has(profile.summary),
    },
    {
      key: "experience",
      label: "Experience",
      weight: 15,
      why: "Internships, freelance work and part-time jobs all improve matching quality.",
      done: profile.work_experience.length > 0,
    },
    {
      key: "education",
      label: "Education",
      weight: 10,
      why: "Education provides additional context for more accurate recommendations.",
      done: profile.education.length > 0,
    },
    {
      key: "skills",
      label: "Skills",
      weight: 10,
      why: "Skills help AI understand which opportunities best match your background.",
      done: profile.skills.length >= 3,
    },
    {
      key: "target_roles",
      label: "Target roles",
      weight: 10,
      why: "Target roles tell us exactly which jobs to hunt for.",
      done: profile.target_roles.length > 0,
    },
    {
      key: "tools",
      label: "Tools",
      weight: 5,
      why: "The tools you use are strong matching keywords for recruiters and ATS.",
      done: profile.tools.length > 0,
    },
    {
      key: "locations",
      label: "Preferred locations",
      weight: 5,
      why: "Location preferences filter out jobs you'd never take.",
      done: profile.preferred_locations.length > 0,
    },
    {
      key: "contact",
      label: "Phone & location",
      weight: 5,
      why: "Complete contact details make your resume header stronger.",
      done: has(profile.basic_info.phone) && has(profile.basic_info.location),
    },
    {
      key: "linkedin",
      label: "LinkedIn",
      weight: 5,
      why: "Adding your LinkedIn gives recruiters another way to learn about your experience.",
      done: has(profile.links.linkedin),
    },
    {
      key: "portfolio",
      label: "Portfolio",
      weight: 5,
      why: "A portfolio helps recruiters see your work. Don't have one? You can add it later.",
      done: has(profile.links.portfolio) || has(profile.links.github),
    },
  ];

  const percent = items.reduce((sum, i) => sum + (i.done ? i.weight : 0), 0);
  return {
    percent,
    completed: items.filter((i) => i.done),
    pending: items.filter((i) => !i.done),
  };
}
