import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export const SOUNDS = [
  'Tech-House', 'House', 'Minimal House', 'Left Field House & Techno',
  'Melodic', 'Melodic Commercial', 'Progressive Techno', 'Techno',
  'Afro House', 'UKG', 'Bounce / Hardhouse', 'Disco', 'Hip-Hop',
  'Dub / Reggae', 'Live',
] as const

export const TIERS = ['A+', 'A', 'B', 'Watch'] as const
export const BUCKETS = {
  book_now_sellout:    'Book Now (Sell Out)',
  book_now_future:     'Book Now (Future)',
  watch_nl:            'Watch NL',
  watch_international: 'Watch International',
} as const

// GET /api/sounds — all frameworks, grouped by sound
export async function GET() {
  try {
    const supabase = createServiceClient()
    const { data, error } = await supabase
      .from('lofi_sound_framework')
      .select(`
        id, sound, tier, bucket, added_by, notes, created_at,
        artists (id, name, slug, candidate_status,
          artist_chartmetric (image_url, genres, sp_monthly_listeners)
        )
      `)
      .order('sound')
      .order('tier')

    if (error) throw error
    return NextResponse.json(data ?? [])
  } catch (err) {
    console.error('[GET /api/sounds]', err)
    return NextResponse.json({ error: 'Failed to fetch sound framework' }, { status: 500 })
  }
}

// POST /api/sounds — add or update an artist in a sound framework
export async function POST(req: Request) {
  try {
    const { sound, artist_id, tier, bucket, added_by, notes } = await req.json()
    if (!sound || !artist_id || !tier || !bucket) {
      return NextResponse.json({ error: 'sound, artist_id, tier, bucket are required' }, { status: 400 })
    }

    const supabase = createServiceClient()
    const { data, error } = await supabase
      .from('lofi_sound_framework')
      .upsert({ sound, artist_id, tier, bucket, added_by: added_by ?? 'LOFI', notes }, {
        onConflict: 'sound,artist_id',
      })
      .select()
      .single()

    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('[POST /api/sounds]', err)
    return NextResponse.json({ error: 'Failed to save assignment' }, { status: 500 })
  }
}
