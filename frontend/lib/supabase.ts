import { createClient, SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

function isValidUrl(value?: string): boolean {
  if (!value) return false;
  try {
    new URL(value);
    return true;
  } catch {
    return false;
  }
}

export const supabaseConfigured = isValidUrl(supabaseUrl) && !!supabaseAnonKey;

// Left null when misconfigured instead of throwing, so a bad/missing env
// var shows a friendly in-app error instead of crashing the whole page.
// Always check `supabaseConfigured` before using this.
export const supabase = supabaseConfigured
  ? createClient(supabaseUrl as string, supabaseAnonKey as string)
  : (null as unknown as SupabaseClient);
