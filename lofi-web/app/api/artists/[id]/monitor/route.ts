import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

// GET: which groups is this artist in?
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params
    const supabase = createServiceClient()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data, error } = await (supabase as any)
      .from('monitor_group_members')
      .select('group_id, notes, added_at, monitor_groups(id, name, color)')
      .eq('artist_id', id)
    if (error) throw error
    return NextResponse.json(data ?? [])
  } catch (err) {
    console.error('[GET /api/artists/[id]/monitor]', err)
    return NextResponse.json({ error: 'Failed to fetch memberships' }, { status: 500 })
  }
}
