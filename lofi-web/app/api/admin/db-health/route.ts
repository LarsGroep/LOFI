import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET() {
  try {
    const supabase = createServiceClient()

    const [
      totalRes, activeRes, excludedDetailRes,
      missingMlRes, missingLofiRes, missingGenresRes,
      byStatusRes, nameListRes,
      cmCountRes, raCountRes, predCountRes, memoCountRes, lastfmCountRes,
      pfCountRes, tracksCountRes,
    ] = await Promise.all([
      supabase.from('artists').select('*', { count: 'exact', head: true }),
      supabase.from('artists').select('*', { count: 'exact', head: true }).eq('excluded', false),
      supabase.from('artists').select('id, name, candidate_status, excluded_reason').eq('excluded', true),
      supabase.from('artist_chartmetric').select('*', { count: 'exact', head: true }).is('ml_features', null),
      supabase.from('artists').select('*', { count: 'exact', head: true }).is('lofi_feel', null),
      supabase.from('artist_chartmetric').select('*', { count: 'exact', head: true }).is('genres', null),
      supabase.from('artists').select('candidate_status').eq('excluded', false),
      supabase.from('artists').select('id, name').eq('excluded', false),
      supabase.from('artist_chartmetric').select('artist_id'),
      supabase.from('artist_ra').select('artist_id'),
      supabase.from('xgboost_predictions').select('artist_id'),
      supabase.from('artist_ai_memo').select('artist_id', { count: 'exact', head: true }),
      supabase.from('artist_lastfm').select('artist_id', { count: 'exact', head: true }),
      supabase.from('artist_partyflock').select('artist_id', { count: 'exact', head: true }),
      supabase.from('artist_cm_tracks').select('*', { count: 'exact', head: true }),
    ])

    const totalCount = totalRes.count ?? 0
    const activeCount = activeRes.count ?? 0

    // Excluded breakdown by reason
    const excludedRows = excludedDetailRes.data ?? []
    const reasonMap = new Map<string, number>()
    for (const r of excludedRows) {
      const reason = (r.excluded_reason as string) ?? 'unknown'
      reasonMap.set(reason, (reasonMap.get(reason) ?? 0) + 1)
    }
    const excludedByReason = [...reasonMap.entries()]
      .map(([reason, count]) => ({ reason, count }))
      .sort((a, b) => b.count - a.count)

    // Coverage gaps (artists without coverage rows)
    const cmIds = new Set((cmCountRes.data ?? []).map((r: { artist_id: string }) => r.artist_id))
    const raIds = new Set((raCountRes.data ?? []).map((r: { artist_id: string }) => r.artist_id))
    const predIds = new Set((predCountRes.data ?? []).map((r: { artist_id: string }) => r.artist_id))

    const allActive = (nameListRes.data ?? []) as { id: string; name: string }[]
    let missingCm = 0, missingRa = 0, missingPredictions = 0
    const nameCounts = new Map<string, number>()
    for (const a of allActive) {
      if (!cmIds.has(a.id)) missingCm++
      if (!raIds.has(a.id)) missingRa++
      if (!predIds.has(a.id)) missingPredictions++
      nameCounts.set(a.name, (nameCounts.get(a.name) ?? 0) + 1)
    }

    const duplicateNames = [...nameCounts.entries()]
      .filter(([, c]) => c > 1)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)

    // Status breakdown (active only)
    const byStatus: Record<string, number> = {}
    for (const r of (byStatusRes.data ?? [])) {
      const s = (r.candidate_status as string) ?? 'unknown'
      byStatus[s] = (byStatus[s] ?? 0) + 1
    }

    // Scheduled for deletion count
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { count: scheduledCount } = await (supabase as any)
      .from('artists')
      .select('id', { count: 'exact', head: true })
      .eq('scheduled_delete', true)

    return NextResponse.json({
      total: totalCount,
      active: activeCount,
      excluded: excludedRows.length,
      scheduledDelete: scheduledCount ?? 0,
      excludedByReason,
      missingChartmetric: missingCm,
      missingRA: missingRa,
      missingMLFeatures: missingMlRes.count ?? 0,
      missingLOFIScore: missingLofiRes.count ?? 0,
      missingPredictions,
      missingGenres: missingGenresRes.count ?? 0,
      byStatus: Object.entries(byStatus)
        .map(([status, count]) => ({ status, count }))
        .sort((a, b) => b.count - a.count),
      duplicateNames,
      tableSizes: {
        artists: totalCount,
        artist_chartmetric: cmIds.size,
        artist_ra: raIds.size,
        xgboost_predictions: predIds.size,
        artist_ai_memo: memoCountRes.count ?? 0,
        artist_lastfm: lastfmCountRes.count ?? 0,
        artist_partyflock: pfCountRes.count ?? 0,
        artist_cm_tracks: tracksCountRes.count ?? 0,
      },
    })
  } catch (err) {
    console.error('[GET /api/admin/db-health]', err)
    return NextResponse.json({ error: 'Failed to fetch DB health' }, { status: 500 })
  }
}
