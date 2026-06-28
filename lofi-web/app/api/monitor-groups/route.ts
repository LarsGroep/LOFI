import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET() {
  try {
    const supabase = createServiceClient()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data, error } = await (supabase as any)
      .from('monitor_groups')
      .select(`
        id, name, description, color, created_at, rescrape_interval_hours, last_scraped_at,
        monitor_group_members (
          id, artist_id, notes, added_at,
          artists (
            id, name, candidate_status, lofi_feel,
            artist_chartmetric ( image_url, genres, sp_monthly_listeners, ml_features, cpp_score ),
            xgboost_predictions ( predicted_growth_90d )
          )
        )
      `)
      .order('created_at')
    if (error) throw error
    return NextResponse.json(data ?? [])
  } catch (err) {
    console.error('[GET /api/monitor-groups]', err)
    return NextResponse.json({ error: 'Failed to fetch groups' }, { status: 500 })
  }
}

export async function POST(req: Request) {
  try {
    const { name, description, color } = await req.json()
    if (!name?.trim()) return NextResponse.json({ error: 'name required' }, { status: 400 })
    const supabase = createServiceClient()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data, error } = await (supabase as any)
      .from('monitor_groups')
      .insert({ name: name.trim(), description: description ?? null, color: color ?? '#6366f1' })
      .select()
      .single()
    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('[POST /api/monitor-groups]', err)
    return NextResponse.json({ error: 'Failed to create group' }, { status: 500 })
  }
}
