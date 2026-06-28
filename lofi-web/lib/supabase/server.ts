import { createServerClient } from '@supabase/ssr'
import { createClient as createSupabaseClient } from '@supabase/supabase-js'
import { cookies } from 'next/headers'
import type { Database } from '@/types/supabase'

// Support both NEXT_PUBLIC_ names (new) and legacy names already in Vercel
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL ?? ''
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? process.env.SUPABASE_KEY ?? ''
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY ?? supabaseAnonKey

export async function createClient() {
  const cookieStore = await cookies()
  return createServerClient<Database>(supabaseUrl, supabaseAnonKey, {
    db: { schema: 'tinder' },
    cookies: {
      getAll() { return cookieStore.getAll() },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        } catch { /* Server Component — safe to ignore */ }
      },
    },
  })
}

// Service-role client for API routes (bypasses RLS, tinder schema).
// Returns `any` because the Database type only covers `public` schema, but all app
// tables live in `tinder` — the generated type is wrong, so we skip it to avoid `never`.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function createServiceClient(): any {
  return createSupabaseClient(supabaseUrl, supabaseServiceKey, {
    db: { schema: 'tinder' },
  })
}
