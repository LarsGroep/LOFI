import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function DELETE(_req: Request, { params }: { params: Promise<{ groupId: string }> }) {
  try {
    const { groupId } = await params
    const supabase = createServiceClient()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { error } = await (supabase as any).from('monitor_groups').delete().eq('id', groupId)
    if (error) throw error
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('[DELETE /api/monitor-groups/[groupId]]', err)
    return NextResponse.json({ error: 'Failed to delete group' }, { status: 500 })
  }
}

// PATCH: add or remove an artist from the group
export async function PATCH(req: Request, { params }: { params: Promise<{ groupId: string }> }) {
  try {
    const { groupId } = await params
    const { artist_id, action, notes } = await req.json()
    if (!artist_id || !action) return NextResponse.json({ error: 'artist_id and action required' }, { status: 400 })
    const supabase = createServiceClient()
    if (action === 'add') {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { data, error } = await (supabase as any)
        .from('monitor_group_members')
        .upsert({ group_id: groupId, artist_id, notes: notes ?? null }, { onConflict: 'group_id,artist_id' })
        .select()
        .single()
      if (error) throw error
      return NextResponse.json(data)
    } else if (action === 'remove') {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { error } = await (supabase as any)
        .from('monitor_group_members')
        .delete()
        .eq('group_id', groupId)
        .eq('artist_id', artist_id)
      if (error) throw error
      return NextResponse.json({ ok: true })
    }
    return NextResponse.json({ error: 'action must be add or remove' }, { status: 400 })
  } catch (err) {
    console.error('[PATCH /api/monitor-groups/[groupId]]', err)
    return NextResponse.json({ error: 'Failed to update group membership' }, { status: 500 })
  }
}
