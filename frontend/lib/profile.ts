import type { ExperienceEntry } from "@/components/ExperienceSection";

export interface EducationEntry {
  school: string;
  degree: string;
  field_of_study: string;
  start_date: string;
  end_date: string;
}

export const emptyEducation = (): EducationEntry => ({
  school: "",
  degree: "",
  field_of_study: "",
  start_date: "",
  end_date: "",
});

export interface Links {
  linkedin: string;
  portfolio: string;
  github: string;
}

export interface BasicInfo {
  full_name: string;
  email: string;
  phone: string;
  location: string;
}

// Same shape whether it came from AI resume parsing or manual entry —
// job_category/experience_level/preferred_locations/work_type are
// onboarding-only fields layered on top of the parsed-resume shape.
export interface Profile {
  basic_info: BasicInfo;
  summary: string;
  work_experience: ExperienceEntry[];
  education: EducationEntry[];
  target_roles: string[];
  skills: string[];
  tools: string[];
  links: Links;
  confidence_flags: Record<string, string>;
  job_category: string;
  experience_level: string;
  preferred_locations: string[];
  work_type: string[];
  resume_template: string; // 'modern' | 'classic' | 'minimal'
}

export function emptyProfile(): Profile {
  return {
    basic_info: { full_name: "", email: "", phone: "", location: "" },
    summary: "",
    work_experience: [],
    education: [],
    target_roles: [],
    skills: [],
    tools: [],
    links: { linkedin: "", portfolio: "", github: "" },
    confidence_flags: {},
    job_category: "",
    experience_level: "junior",
    preferred_locations: [],
    work_type: [],
    resume_template: "modern",
  };
}

// Merges an AI-parsed profile (from /api/resumes/parse-status) with the
// onboarding-only defaults it doesn't include.
export function profileFromParsed(parsed: Partial<Profile>): Profile {
  return { ...emptyProfile(), ...parsed };
}
