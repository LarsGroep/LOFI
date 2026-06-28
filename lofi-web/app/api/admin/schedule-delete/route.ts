import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

// POST /api/admin/schedule-delete — mark an artist for deletion
export async function POST(req: Request) {
  try {
    const { artist_id, reason } = await req.json()
    if (!artist_id) return NextResponse.json({ error: 'artist_id required' }, { status: 400 })
    const supabase = createServiceClient()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { error } = await (supabase as any)
      .from('artists')
      .update({
        scheduled_delete: true,
        scheduled_delete_reason: reason ?? 'AI verdict: far outlier from target cohort',
        excluded: true,
        candidate_status: 'rejected',
      })
      .eq('id', artist_id)
    if (error) throw error
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('[POST /api/admin/schedule-delete]', err)
    return NextResponse.json({ error: 'Failed to schedule deletion' }, { status: 500 })
  }
}

// DELETE /api/admin/schedule-delete — execute all scheduled deletions
export async function DELETE() {
  try {
    const supabase = createServiceClient()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { count } = await (supabase as any)
      .from('artists')
      .select('id', { count: 'exact', head: true })
      .eq('scheduled_delete', true)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { error } = await (supabase as any)
      .from('artists')
      .delete()
      .eq('scheduled_delete', true)
    if (error) throw error
    return NextResponse.json({ ok: true, deleted: count ?? 0 })
  } catch (err) {
    console.error('[DELETE /api/admin/schedule-delete]', err)
    return NextResponse.json({ error: 'Failed to execute deletions' }, { status: 500 })
  }
}
