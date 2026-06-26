import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'
import type { ArtistDetail, RaEventSummary, TimeseriesPoint } from '@/types/supabase'

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  try {
    const supabase = createServiceClient()

    const [artistRes, raEventsRes, feedbackRes, notesRes] = await Promise.all([
      supabase
        .from('artists')
        .select(`
          id, name, slug, candidate_status, lofi_feel,
          booked_similar_count, booked_neighbor_count, updated_at,
          artist_chartmetric (
            image_url, cover_url, description, career_status,
            record_label, booking_agent, genres,
            sp_monthly_listeners, sp_followers, sp_popularity,
            ig_followers, tiktok_followers, yt_subscribers,
            soundcloud_followers, cpp_score, cm_artist_score,
            hometown_city, current_city, cm_timeseries
          ),
          artist_ra (event_count),
          artist_partyflock (pf_fans, pf_total_performances),
          artist_lastfm (lfm_listeners, tags),
          xgboost_predictions (predicted_growth_90d, missing_pct),
          artist_ai_memo (*)
        `)
        .eq('id', id)
        .single(),

      supabase
        .from('ra_events')
        .select('event_id, date, venue, city, country, venue_capacity')
        .eq('artist_id', id)
        .order('date', { ascending: false })
        .limit(50),

      supabase
        .from('artist_feedback')
        .select('*')
        .eq('artist_id', id)
        .order('created_at', { ascending: false }),

      supabase
        .from('artist_notes')
        .select('*')
        .eq('artist_id', id)
        .order('created_at', { ascending: false }),
    ])

    if (artistRes.error) throw artistRes.error
    const row = artistRes.data

    const cm = Array.isArray(row.artist_chartmetric) ? row.artist_chartmetric[0] : row.artist_chartmetric
    const ra = Array.isArray(row.artist_ra) ? row.artist_ra[0] : row.artist_ra
    const pf = Array.isArray(row.artist_partyflock) ? row.artist_partyflock[0] : row.artist_partyflock
    const lfm = Array.isArray(row.artist_lastfm) ? row.artist_lastfm[0] : row.artist_lastfm
    const xg = Array.isArray(row.xgboost_predictions) ? row.xgboost_predictions[0] : row.xgboost_predictions
    const memo = Array.isArray(row.artist_ai_memo) ? row.artist_ai_memo[0] : row.artist_ai_memo
    const lofi = row.lofi_feel as Record<string, unknown> | null

    // Extract Spotify listener timeseries for the chart (monthly samples, last 12 months)
    let timeseries: TimeseriesPoint[] | null = null
    if (cm?.cm_timeseries) {
      const ts = cm.cm_timeseries as Record<string, { date: string; value: number }[]>
      const pts = ts?.spotify?.listeners
      if (pts?.length) {
        const cutoff = new Date()
        cutoff.setFullYear(cutoff.getFullYear() - 1)
        const cutoffStr = cutoff.toISOString().slice(0, 10)
        // Sample weekly to keep payload small
        const filtered = pts
          .filter(p => p.date >= cutoffStr)
          .filter((_, i) => i % 7 === 0)
        timeseries = filtered.map(p => ({ date: p.date, listeners: p.value }))
      }
    }

    const detail: ArtistDetail = {
      id: row.id,
      name: row.name,
      slug: row.slug,
      status: row.candidate_status as ArtistDetail['status'],
      imageUrl: cm?.image_url ?? null,
      coverUrl: cm?.cover_url ?? null,
      genres: cm?.genres ?? null,
      description: cm?.description ?? null,
      careerStatus: cm?.career_status ?? null,
      recordLabel: cm?.record_label ?? null,
      bookingAgent: cm?.booking_agent ?? null,
      hometownCity: cm?.hometown_city ?? null,
      currentCity: cm?.current_city ?? null,
      spMonthlyListeners: cm?.sp_monthly_listeners ?? null,
      spFollowers: cm?.sp_followers ?? null,
      spPopularity: cm?.sp_popularity ?? null,
      igFollowers: cm?.ig_followers ?? null,
      tiktokFollowers: cm?.tiktok_followers ?? null,
      ytSubscribers: cm?.yt_subscribers ?? null,
      soundcloudFollowers: cm?.soundcloud_followers ?? null,
      cppScore: cm?.cpp_score ?? null,
      cmArtistScore: cm?.cm_artist_score ?? null,
      lofiFeel: lofi ? (lofi as ArtistDetail['lofiFeel']) : null,
      pfFans: pf?.pf_fans ?? null,
      pfTotalPerformances: pf?.pf_total_performances ?? null,
      lfmListeners: lfm?.lfm_listeners ?? null,
      lfmTags: lfm?.tags ?? null,
      raEventCount: ra?.event_count ?? null,
      xgboostGrowth90d: xg?.predicted_growth_90d ?? null,
      missingDataPct: xg?.missing_pct ?? null,
      bookedSimilarCount: row.booked_similar_count,
      bookedNeighborCount: row.booked_neighbor_count,
      timeseries,
      raEvents: (raEventsRes.data ?? []) as RaEventSummary[],
      feedback: feedbackRes.data ?? [],
      aiMemo: memo ?? null,
      updatedAt: row.updated_at ?? null,
    }

    return NextResponse.json(detail)
  } catch (err) {
    console.error('[GET /api/artists/[id]]', err)
    return NextResponse.json({ error: 'Failed to fetch artist' }, { status: 500 })
  }
}

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  try {
    const body = await req.json()
    const allowed = ['candidate_status']
    const update: Record<string, unknown> = {}
    for (const key of allowed) {
      if (key in body) update[key] = body[key]
    }
    if (Object.keys(update).length === 0) {
      return NextResponse.json({ error: 'No valid fields to update' }, { status: 400 })
    }

    const supabase = createServiceClient()
    const { error } = await supabase.from('artists').update(update).eq('id', id)
    if (error) throw error
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('[PATCH /api/artists/[id]]', err)
    return NextResponse.json({ error: 'Failed to update artist' }, { status: 500 })
  }
}
