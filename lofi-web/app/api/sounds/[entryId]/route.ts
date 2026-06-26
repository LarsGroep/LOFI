import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

// DELETE /api/sounds/[entryId]
export async function DELETE(_req: Request, { params }: { params: Promise<{ entryId: string }> }) {
  const { entryId } = await params
  try {
    const supabase = createServiceClient()
    const { error } = await supabase
      .from('lofi_sound_framework')
      .delete()
      .eq('id', entryId)

    if (error) throw error
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('[DELETE /api/sounds/[entryId]]', err)
    return NextResponse.json({ error: 'Failed to delete assignment' }, { status: 500 })
  }
}

// PATCH /api/sounds/[entryId] — update tier or bucket
export async function PATCH(req: Request, { params }: { params: Promise<{ entryId: string }> }) {
  const { entryId } = await params
  try {
    const body = await req.json()
    const allowed = ['tier', 'bucket', 'notes']
    const update: Record<string, unknown> = {}
    for (const key of allowed) {
      if (key in body) update[key] = body[key]
    }

    const supabase = createServiceClient()
    const { data, error } = await supabase
      .from('lofi_sound_framework')
      .update(update)
      .eq('id', entryId)
      .select()
      .single()

    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('[PATCH /api/sounds/[entryId]]', err)
    return NextResponse.json({ error: 'Failed to update assignment' }, { status: 500 })
  }
}
