import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'
import type { ArtistListItem } from '@/types/supabase'

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url)
    const limit = Math.min(Number(searchParams.get('limit') ?? 200), 2000)
    const offset = Number(searchParams.get('offset') ?? 0)
    const status = searchParams.get('status')
    const genre = searchParams.get('genre')
    const q = searchParams.get('q')

    const supabase = createServiceClient()

    // Match Streamlit cohort: only artists with XGBoost predictions (inner join).
    // Streamlit's _load_catalogue_data() uses predictions_df as the primary table.
    let query = supabase
      .from('artists')
      .select(`
        id, name, slug, candidate_status, lofi_feel, excluded,
        booked_similar_count, booked_neighbor_count,
        artist_chartmetric (image_url, genres, sp_monthly_listeners, booking_agent, ml_features),
        artist_ra (event_count),
        xgboost_predictions!inner (predicted_growth_90d),
        artist_ai_memo (verdict, verdict_reason, generated_at)
      `)
      .eq('excluded', false)
      .order('name')
      .range(offset, offset + limit - 1)

    if (status && status !== 'all') {
      query = query.eq('candidate_status', status)
    }
    if (q) {
      query = query.ilike('name', `%${q}%`)
    }

    const { data: rawData, error } = await query
    if (error) throw error

    // Filter by genre client-side (PostgREST cannot filter on embedded JSONB array)
    const data = genre
      ? (rawData ?? []).filter(row => {
          const cm = Array.isArray(row.artist_chartmetric) ? row.artist_chartmetric[0] : row.artist_chartmetric
          return (cm?.genres as string[] | null)?.some(g => g.toLowerCase() === genre.toLowerCase())
        })
      : rawData

    const items: ArtistListItem[] = (data ?? []).map((row) => {
      const cm = Array.isArray(row.artist_chartmetric) ? row.artist_chartmetric[0] : row.artist_chartmetric
      const ra = Array.isArray(row.artist_ra) ? row.artist_ra[0] : row.artist_ra
      const xg = Array.isArray(row.xgboost_predictions) ? row.xgboost_predictions[0] : row.xgboost_predictions
      const memo = Array.isArray(row.artist_ai_memo) ? row.artist_ai_memo[0] : row.artist_ai_memo

      const lofi = row.lofi_feel as { score?: number } | null
      const ml = (cm?.ml_features ?? null) as Record<string, number | null> | null
      const sp30d = ml?.sp_listeners_30d_pct ?? null

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
        spotifyDelta30d: sp30d,
        excluded: row.excluded ?? false,
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
