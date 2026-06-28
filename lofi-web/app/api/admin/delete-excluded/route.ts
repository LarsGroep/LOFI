import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

// DELETE /api/admin/delete-excluded — hard-delete all excluded=true artists
export async function DELETE() {
  try {
    const supabase = createServiceClient()

    // Count first
    const { count } = await supabase
      .from('artists')
      .select('id', { count: 'exact', head: true })
      .eq('excluded', true)

    // Delete
    const { error } = await supabase
      .from('artists')
      .delete()
      .eq('excluded', true)
    if (error) throw error

    return NextResponse.json({ ok: true, deleted: count ?? 0 })
  } catch (err) {
    console.error('[DELETE /api/admin/delete-excluded]', err)
    return NextResponse.json({ error: 'Failed to delete excluded artists' }, { status: 500 })
  }
}
