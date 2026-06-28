import { NextResponse } from 'next/server'

const CM_BASE = 'https://api.chartmetric.com/api'

async function getCmToken(): Promise<string | null> {
  const rt = process.env.CHARTMETRIC_REFRESH_TOKEN?.trim()
  if (!rt) return null
  try {
    const res = await fetch(`${CM_BASE}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refreshtoken: rt }),
    })
    if (!res.ok) return null
    const data = await res.json()
    return data.token ?? null
  } catch {
    return null
  }
}

export interface CmArtistMatch {
  id: number
  name: string
  image_url: string | null
  genres: string[]
  sp_monthly_listeners: number | null
  cm_artist_score: number | null
  city: string | null
  country: string | null
}

export async function GET(req: Request) {
  const q = new URL(req.url).searchParams.get('q')?.trim()
  if (!q || q.length < 2) return NextResponse.json([])

  const token = await getCmToken()
  if (!token) {
    return NextResponse.json({ error: 'Chartmetric token not configured. Set CHARTMETRIC_REFRESH_TOKEN in environment settings.' }, { status: 503 })
  }

  try {
    const res = await fetch(`${CM_BASE}/artist/search?q=${encodeURIComponent(q)}&limit=8&offset=0`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`CM API ${res.status}`)
    const data = await res.json()

    const artists: CmArtistMatch[] = (data.obj ?? []).map((a: Record<string, unknown>) => ({
      id: a.id,
      name: a.name,
      image_url: a.image_url ?? null,
      genres: (a.genres as string[] | null) ?? [],
      sp_monthly_listeners: (a.sp_monthly_listeners as number | null) ?? null,
      cm_artist_score: (a.cm_artist_score as number | null) ?? null,
      city: (a.city as string | null) ?? null,
      country: (a.country as string | null) ?? null,
    }))
    return NextResponse.json(artists)
  } catch (err) {
    console.error('[GET /api/artists/chartmetric-search]', err)
    return NextResponse.json({ error: 'Chartmetric search failed' }, { status: 500 })
  }
}

// POST: commit a Chartmetric artist to the DB and trigger enrichment
export async function POST(req: Request) {
  const { cm_artist_id, name } = await req.json()
  if (!cm_artist_id && !name) {
    return NextResponse.json({ error: 'cm_artist_id or name required' }, { status: 400 })
  }
  try {
    // Add to discovery queue — the pipeline will pick it up and scrape
    const { createServiceClient } = await import('@/lib/supabase/server')
    const supabase = createServiceClient()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data, error } = await (supabase as any)
      .from('discovery_queue')
      .insert({
        artist_name: name,
        cm_artist_id: cm_artist_id ?? null,
        source: 'manual_cm',
        signal: 'user_add',
      })
      .select()
      .single()
    if (error) throw error
    return NextResponse.json({ ok: true, queued: data })
  } catch (err) {
    console.error('[POST /api/artists/chartmetric-search]', err)
    return NextResponse.json({ error: 'Failed to queue artist' }, { status: 500 })
  }
}
