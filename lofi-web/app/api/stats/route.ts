import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET() {
  try {
    const supabase = createServiceClient()

    const [totalRes, bookedRes, trendingRes, withMemoRes] = await Promise.all([
      supabase.from('artists').select('*', { count: 'exact', head: true }),
      supabase.from('artists').select('*', { count: 'exact', head: true }).eq('candidate_status', 'booked'),
      supabase
        .from('xgboost_predictions')
        .select('*', { count: 'exact', head: true })
        .gt('predicted_growth_90d', 10),
      supabase
        .from('artist_ai_memo')
        .select('*', { count: 'exact', head: true }),
    ])

    return NextResponse.json({
      total: totalRes.count ?? 0,
      booked: bookedRes.count ?? 0,
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
