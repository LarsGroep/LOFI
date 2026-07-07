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
    const res = await fetch(`${CM_BASE}/search?q=${encodeURIComponent(q)}&type=artists&limit=8`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`CM API ${res.status}`)
    const data = await res.json()

    const artists: CmArtistMatch[] = (data.obj?.artists ?? []).map((a: Record<string, unknown>) => ({
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

// POST: create the artist profile and immediately trigger a scrape
export async function POST(req: Request) {
  const { cm_artist_id, name } = await req.json()
  if (!name?.trim()) {
    return NextResponse.json({ error: 'name required' }, { status: 400 })
  }
  try {
    const { createServiceClient } = await import('@/lib/supabase/server')
    const { slugify, dispatchArtistScrape } = await import('@/lib/scrape-dispatch')
    const supabase = createServiceClient()
    const { data, error } = await supabase
      .from('artists')
      .insert({
        name: name.trim(),
        slug: slugify(name),
        chartmetric_id: cm_artist_id ? String(cm_artist_id) : null,
        candidate_status: 'pending',
        needs_scraping: true,
      })
      .select('id, name')
      .single()
    if (error) {
      if (error.code === '23505') {
        return NextResponse.json({ error: `"${name}" is already being tracked` }, { status: 409 })
      }
      throw error
    }
    const scrapeStarted = await dispatchArtistScrape(data.id)
    return NextResponse.json({ ok: true, artist: data, scrapeStarted })
  } catch (err) {
    console.error('[POST /api/artists/chartmetric-search]', err)
    return NextResponse.json({ error: 'Failed to add artist' }, { status: 500 })
  }
}
