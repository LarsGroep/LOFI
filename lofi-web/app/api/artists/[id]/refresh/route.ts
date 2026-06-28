import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

function clamp(v: number, lo = 0, hi = 100) { return Math.max(lo, Math.min(hi, isNaN(v) ? 0 : v)) }

function pctToScore(pct: number | null | undefined, scale = 30): number {
  if (pct == null) return 50
  return clamp(50 + 50 * Math.tanh(pct / scale))
}

function rankToScore(rank: number | null | undefined, maxRank = 200_000): number {
  if (rank == null || rank === 0) return 0
  return clamp(100 * (1 - rank / maxRank))
}

export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params
    const supabase = createServiceClient()

    const { data: cm, error: cmErr } = await supabase
      .from('artist_chartmetric')
      .select(`
        cm_artist_score, cm_artist_rank, fan_base_rank,
        career_stage_score, career_trend_score, cpp_score,
        sp_monthly_listeners, ig_followers, ml_features
      `)
      .eq('artist_id', id)
      .single()

    if (cmErr || !cm) return NextResponse.json({ error: 'No Chartmetric data for artist' }, { status: 404 })

    const ml = (cm.ml_features ?? {}) as Record<string, number | null>

    // ML features — same keys as five_scores.py
    const sp30   = ml.sp_listeners_30d_pct ?? null
    const sp90   = ml.sp_listeners_90d_pct ?? null
    const sp180  = ml.sp_listeners_180d_pct ?? null
    const accel  = ml.sp_listeners_accel ?? null
    const xpm    = ml.cross_platform_momentum_30d ?? null
    const platG  = ml.platforms_growing_30d ?? null
    const cpp30  = ml.cpp_score_30d_pct ?? null
    const cpp90  = ml.cpp_score_90d_pct ?? null
    const cppCur = ml.cpp_score_current ?? null

    // Profile fields
    const cmScore    = cm.cm_artist_score ?? null
    const cmRank     = cm.cm_artist_rank ?? null
    const fanRank    = cm.fan_base_rank ?? null
    const careerStg  = cm.career_stage_score ?? null
    const careerTrnd = cm.career_trend_score ?? null
    const spList     = cm.sp_monthly_listeners ?? null
    const igFollow   = cm.ig_followers ?? null
    const cppScore   = cm.cpp_score ?? null

    // 1. Momentum
    const mSp30  = pctToScore(sp30, 20)
    const mXpm   = pctToScore(xpm, 25)
    const mPlat  = platG != null ? clamp(platG / 5 * 100) : 50
    const mCpp30 = pctToScore(cpp30, 8)
    const momentum = clamp(0.35 * mSp30 + 0.30 * mXpm + 0.20 * mPlat + 0.15 * mCpp30)

    // 2. Growth (acceleration primary)
    const gAccel = clamp(50 + (accel ?? 0) * 2)
    const gSp30  = pctToScore(sp30, 20)
    const gTrend = clamp((careerTrnd ?? 0) * 10 + 50)
    const growth = clamp(0.50 * gAccel + 0.30 * gSp30 + 0.20 * gTrend)

    // 3. Market Relevance
    const rCm   = clamp(cmScore ?? 0)
    const rRank = rankToScore(cmRank)
    const rFan  = rankToScore(fanRank)
    const rCpp  = clamp(((cppScore ?? cppCur ?? 0) / 10) * 100)
    const market_relevance = clamp(0.35 * rCm + 0.25 * rRank + 0.25 * rFan + 0.15 * rCpp)

    // 4. Future Potential
    const f180   = pctToScore(sp180, 60)
    const fAccel = clamp(50 + (accel ?? 0) * 1.5)
    const fStage = clamp((careerStg ?? 0) * 10 + 50)
    const fCpp90 = pctToScore(cpp90, 15)
    const future_potential = clamp(0.35 * f180 + 0.30 * fAccel + 0.20 * fStage + 0.15 * fCpp90)

    // 5. Confidence — data coverage (13 fields, same as five_scores.py)
    const fields = [sp30, sp90, sp180, accel, xpm, platG, cppCur, cmScore, cmRank, igFollow, spList, careerStg, careerTrnd]
    const filled = fields.filter(f => f != null).length
    const confidence = clamp((filled / fields.length) * 100)

    const composite = clamp(0.25 * momentum + 0.25 * growth + 0.25 * market_relevance + 0.15 * future_potential + 0.10 * confidence)

    const { error: updateErr } = await supabase
      .from('artists')
      .update({
        lofi_feel: {
          score: Math.round(composite * 10) / 10,
          momentum:         Math.round(momentum * 10) / 10,
          growth:           Math.round(growth * 10) / 10,
          market_relevance: Math.round(market_relevance * 10) / 10,
          future_potential: Math.round(future_potential * 10) / 10,
          confidence:       Math.round(confidence * 10) / 10,
        },
      })
      .eq('id', id)
    if (updateErr) throw updateErr

    return NextResponse.json({ ok: true, composite, momentum, growth, market_relevance, future_potential, confidence })
  } catch (err) {
    console.error('[POST /api/artists/[id]/refresh]', err)
    return NextResponse.json({ error: 'Refresh failed' }, { status: 500 })
  }
}
