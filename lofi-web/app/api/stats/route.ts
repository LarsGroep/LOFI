import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET() {
  try {
    const supabase = createServiceClient()

    const [statusRes, trendingRes, withMemoRes] = await Promise.all([
      supabase
        .from('artists')
        .select('candidate_status'),
      supabase
        .from('xgboost_predictions')
        .select('*', { count: 'exact', head: true })
        .gt('predicted_growth_90d', 10),
      supabase
        .from('artist_ai_memo')
        .select('*', { count: 'exact', head: true }),
    ])

    const rows = statusRes.data ?? []
    const counts = { pending: 0, candidate: 0, accepted: 0, booked: 0, total: rows.length }
    for (const r of rows) {
      const s = r.candidate_status as string | null
      if (s === 'pending') counts.pending++
      else if (s === 'candidate') counts.candidate++
      else if (s === 'accepted') counts.accepted++
      else if (s === 'booked') counts.booked++
    }

    return NextResponse.json({
      total: counts.total,
      pending: counts.pending,
      candidate: counts.candidate,
      accepted: counts.accepted,
      booked: counts.booked,
      trending: trendingRes.count ?? 0,
      withMemo: withMemoRes.count ?? 0,
    }, {
      headers: { 'Cache-Control': 's-maxage=120, stale-while-revalidate=300' },
    })
  } catch (err) {
    console.error('[GET /api/stats]', err)
    return NextResponse.json({ error: 'Failed to fetch stats' }, { status: 500 })
  }
}
