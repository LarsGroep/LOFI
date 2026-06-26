import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET() {
  try {
    const supabase = createServiceClient()

    // Fetch artists with genres + xgboost predictions + listeners
    const { data, error } = await supabase
      .from('artist_chartmetric')
      .select('genres, sp_monthly_listeners, artist_id, artists!inner(candidate_status)')
      .not('genres', 'is', null)
      .limit(2000)

    if (error) throw error

    // Also fetch xgboost for growth data
    const { data: xgData } = await supabase
      .from('xgboost_predictions')
      .select('artist_id, predicted_growth_90d')
      .limit(2000)

    const growthMap = new Map<string, number>()
    for (const x of xgData ?? []) {
      if (x.predicted_growth_90d != null) growthMap.set(x.artist_id, x.predicted_growth_90d)
    }

    // Aggregate by genre
    const genreMap = new Map<string, { count: number; totalListeners: number; totalGrowth: number; growthCount: number }>()
    for (const row of data ?? []) {
      if (!row.genres?.length) continue
      const growth = growthMap.get(row.artist_id)
      for (const genre of row.genres as string[]) {
        const key = genre.toLowerCase()
        if (!genreMap.has(key)) genreMap.set(key, { count: 0, totalListeners: 0, totalGrowth: 0, growthCount: 0 })
        const g = genreMap.get(key)!
        g.count++
        if (row.sp_monthly_listeners) g.totalListeners += row.sp_monthly_listeners
        if (growth != null) { g.totalGrowth += growth; g.growthCount++ }
      }
    }

    const genres = [...genreMap.entries()]
      .filter(([, v]) => v.count >= 5) // only genres with enough artists
      .map(([name, v]) => ({
        name,
        artistCount: v.count,
        avgListeners: v.count > 0 ? Math.round(v.totalListeners / v.count) : 0,
        avgGrowth: v.growthCount > 0 ? v.totalGrowth / v.growthCount : null,
        pctGrowing: v.growthCount > 0
          ? Math.round(((v.totalGrowth > 0 ? 1 : 0) / v.growthCount) * 100)
          : null,
      }))
      .sort((a, b) => b.artistCount - a.artistCount)
      .slice(0, 20)

    return NextResponse.json({ genres })
  } catch (err) {
    console.error('[GET /api/scene]', err)
    return NextResponse.json({ error: 'Failed to fetch scene data' }, { status: 500 })
  }
}
