import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const q = searchParams.get('q')?.trim()

  if (!q || q.length < 2) return NextResponse.json([])

  try {
    const supabase = createServiceClient()
    const { data, error } = await supabase
      .from('artists')
      .select('id, name, candidate_status, excluded, artist_chartmetric(image_url, genres, sp_monthly_listeners)')
      .ilike('name', `%${q}%`)
      .neq('candidate_status', 'rejected')
      .eq('excluded', false)
      .order('name')
      .limit(20)

    if (error) throw error
    return NextResponse.json((data ?? []).map((a: any) => {
      const cm = Array.isArray(a.artist_chartmetric) ? a.artist_chartmetric[0] : a.artist_chartmetric
      return { id: a.id, name: a.name, status: a.candidate_status, imageUrl: cm?.image_url ?? null, genres: cm?.genres ?? null, spMonthlyListeners: cm?.sp_monthly_listeners ?? null }
    }))
  } catch (err) {
    console.error('[GET /api/artists/search]', err)
    return NextResponse.json({ error: 'Search failed' }, { status: 500 })
  }
}

// POST — create the artist profile and immediately trigger a scrape
export async function POST(req: Request) {
  try {
    const { name } = await req.json()
    if (!name?.trim()) return NextResponse.json({ error: 'name required' }, { status: 400 })

    const { slugify, dispatchArtistScrape } = await import('@/lib/scrape-dispatch')
    const supabase = createServiceClient()
    const { data, error } = await supabase
      .from('artists')
      .insert({
        name: name.trim(),
        slug: slugify(name),
        candidate_status: 'pending',
        needs_scraping: true,
      })
      .select('id, name')
      .single()

    if (error) {
      if (error.code === '23505') {
        return NextResponse.json({ error: `"${name.trim()}" is already being tracked` }, { status: 409 })
      }
      throw error
    }
    const scrapeStarted = await dispatchArtistScrape(data.id)
    return NextResponse.json({ ok: true, artist: data, scrapeStarted })
  } catch (err) {
    console.error('[POST /api/artists/search]', err)
    return NextResponse.json({ error: 'Failed to add artist' }, { status: 500 })
  }
}
