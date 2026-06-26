import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'
import type { ArtistListItem } from '@/types/supabase'

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url)
    const limit = Math.min(Number(searchParams.get('limit') ?? 100), 500)
    const offset = Number(searchParams.get('offset') ?? 0)
    const status = searchParams.get('status') // optional filter

    const supabase = createServiceClient()

    let query = supabase
      .from('artists')
      .select(`
        id, name, slug, candidate_status, lofi_feel,
        booked_similar_count, booked_neighbor_count,
        artist_chartmetric (image_url, genres, sp_monthly_listeners, booking_agent),
        artist_ra (event_count),
        xgboost_predictions (predicted_growth_90d),
        artist_ai_memo (verdict, verdict_reason, generated_at)
      `)
      .order('name')
      .range(offset, offset + limit - 1)

    if (status && status !== 'all') {
      query = query.eq('candidate_status', status)
    }

    const { data, error } = await query
    if (error) throw error

    const items: ArtistListItem[] = (data ?? []).map((row) => {
      const cm = Array.isArray(row.artist_chartmetric)
        ? row.artist_chartmetric[0]
        : row.artist_chartmetric
      const ra = Array.isArray(row.artist_ra)
        ? row.artist_ra[0]
        : row.artist_ra
      const xg = Array.isArray(row.xgboost_predictions)
        ? row.xgboost_predictions[0]
        : row.xgboost_predictions
      const memo = Array.isArray(row.artist_ai_memo)
        ? row.artist_ai_memo[0]
        : row.artist_ai_memo

      const lofi = row.lofi_feel as { score?: number } | null

      return {
        id: row.id,
        name: row.name,
        slug: row.slug,
        status: row.candidate_status as ArtistListItem['status'],
        imageUrl: cm?.image_url ?? null,
        genres: cm?.genres ?? null,
        spMonthlyListeners: cm?.sp_monthly_listeners ?? null,
        raEventCount: ra?.event_count ?? null,
        lofiFitScore: lofi?.score ?? null,
        xgboostGrowth90d: xg?.predicted_growth_90d ?? null,
        bookingAgent: cm?.booking_agent ?? null,
        isFavorite: false,
        verdict: memo?.verdict ?? null,
        verdictReason: memo?.verdict_reason ?? null,
        generatedAt: memo?.generated_at ?? null,
        spotifyDelta30d: null,
      }
    })

    return NextResponse.json(items, {
      headers: { 'Cache-Control': 's-maxage=60, stale-while-revalidate=300' },
    })
  } catch (err) {
    console.error('[GET /api/artists]', err)
    return NextResponse.json({ error: 'Failed to fetch artists' }, { status: 500 })
  }
}
