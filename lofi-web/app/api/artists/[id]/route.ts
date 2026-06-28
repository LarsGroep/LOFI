import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'
import type { ArtistDetail, RaEventSummary, TimeseriesPoint, MultiTimeseriesItem, TrackRow, ValidationEventRow } from '@/types/supabase'

// ─── Five Scores ───────────────────────────────────────────────────────────────

function decodeHtmlEntities(s: string | null): string | null {
  if (!s) return s
  return s.replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
          .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
}

function clamp(v: number, lo = 0, hi = 100): number {
  if (isNaN(v) || !isFinite(v)) return lo
  return Math.max(lo, Math.min(hi, v))
}
function pctToScore(pct: number | null | undefined, scale = 30): number {
  if (pct == null) return 50
  return clamp(50 + 50 * Math.tanh(pct / scale))
}
function rankToScore(rank: number | null | undefined, maxRank = 200_000): number {
  if (!rank || rank <= 0) return 0
  return clamp(100 * (1 - rank / maxRank))
}
interface MlFeaturesForScoring {
  sp_listeners_30d_pct?: number | null
  sp_listeners_90d_pct?: number | null
  sp_listeners_180d_pct?: number | null
  sp_listeners_accel?: number | null
  cross_platform_momentum_30d?: number | null
  platforms_growing_30d?: number | null
  cpp_score_30d_pct?: number | null
  cpp_score_90d_pct?: number | null
  cpp_score_current?: number | null
  [key: string]: number | null | undefined
}
function computeFiveScores(
  cm: { cm_artist_score?: number | null; cm_artist_rank?: number | null; fan_base_rank?: number | null; career_stage_score?: number | null; career_trend_score?: number | null; sp_monthly_listeners?: number | null; ig_followers?: number | null },
  ml: MlFeaturesForScoring
) {
  const sp30 = ml.sp_listeners_30d_pct ?? null
  const sp90 = ml.sp_listeners_90d_pct ?? null
  const sp180 = ml.sp_listeners_180d_pct ?? null
  const accel = ml.sp_listeners_accel ?? null
  const xpm = ml.cross_platform_momentum_30d ?? null
  const platG = ml.platforms_growing_30d ?? null
  const cpp30 = ml.cpp_score_30d_pct ?? null
  const cpp90 = ml.cpp_score_90d_pct ?? null
  const cppCur = ml.cpp_score_current ?? null
  const mSp30 = pctToScore(sp30, 20); const mXpm = pctToScore(xpm, 25)
  const mPlat = platG != null ? clamp(platG / 5 * 100) : 50; const mCpp30 = pctToScore(cpp30, 8)
  const momentum = clamp(0.35 * mSp30 + 0.30 * mXpm + 0.20 * mPlat + 0.15 * mCpp30)
  const gAccel = clamp(50 + (accel ?? 0) * 2); const gSp30 = pctToScore(sp30, 20)
  const gTrend = clamp((cm.career_trend_score ?? 0) * 10 + 50)
  const growth = clamp(0.50 * gAccel + 0.30 * gSp30 + 0.20 * gTrend)
  const rCm = clamp(cm.cm_artist_score ?? 0); const rRank = rankToScore(cm.cm_artist_rank)
  const rFan = rankToScore(cm.fan_base_rank); const rCpp = clamp((cppCur ?? 0) / 10 * 100)
  const marketRelevance = clamp(0.35 * rCm + 0.25 * rRank + 0.25 * rFan + 0.15 * rCpp)
  const f180 = pctToScore(sp180, 60); const fAccel = clamp(50 + (accel ?? 0) * 1.5)
  const fStage = clamp((cm.career_stage_score ?? 0) * 10 + 50); const fCpp90 = pctToScore(cpp90, 15)
  const futurePotential = clamp(0.35 * f180 + 0.30 * fAccel + 0.20 * fStage + 0.15 * fCpp90)
  const fields = [sp30, sp90, sp180, accel, xpm, platG, cppCur, cm.cm_artist_score, cm.cm_artist_rank, cm.ig_followers, cm.sp_monthly_listeners, cm.career_stage_score, cm.career_trend_score]
  const filled = fields.filter(f => f != null).length
  const confidence = clamp(filled / fields.length * 100)
  return {
    momentum: Math.round(momentum * 10) / 10,
    growth: Math.round(growth * 10) / 10,
    market_relevance: Math.round(marketRelevance * 10) / 10,
    future_potential: Math.round(futurePotential * 10) / 10,
    confidence: Math.round(confidence * 10) / 10,
    breakdown: { sp_30d_pct: sp30, sp_90d_pct: sp90, accel, cross_platform_30d: xpm, platforms_growing: platG, data_filled: filled, data_total: fields.length },
  }
}

// ─── NL Score (port of compute_nl_score from lofi_pipeline.py) ────────────────

interface NlVenue {
  id: number
  venue_name: string | null
  city: string | null
  country: string | null
  tier: number | null
  ra_venue_name: string | null
  pf_venue_name: string | null
}

export interface NlScoreBreakdown {
  nl_event_count: number
  ams_event_count: number
  ams_score: number
  nl_event_score: number
  demo_pct: number | null
  has_demographics: boolean
}

function extractCountryPct(audience: Record<string, unknown> | null, code: string): number | null {
  if (!audience) return null
  const c = code.toUpperCase()
  // Format: { countries: [{code, pct}] }
  const list1 = audience.countries as { code?: string; pct?: number }[] | null
  if (Array.isArray(list1)) {
    const hit = list1.find(x => (x.code ?? '').toUpperCase() === c)
    if (hit?.pct != null) return hit.pct
  }
  // Format: { audience_geo: { countries: [{code, pct}] } }
  const geo = audience.audience_geo as { countries?: { code?: string; pct?: number }[] } | null
  if (geo?.countries) {
    const hit = geo.countries.find(x => (x.code ?? '').toUpperCase() === c)
    if (hit?.pct != null) return hit.pct
  }
  // Format: direct key { NL: 15.0 }
  if (typeof audience[c] === 'number') return audience[c] as number
  return null
}

function buildVenueLookup(nlVenues: NlVenue[]): Map<string, NlVenue> {
  const m = new Map<string, NlVenue>()
  for (const v of nlVenues) {
    for (const key of [v.ra_venue_name, v.pf_venue_name, v.venue_name]) {
      const k = (key ?? '').toLowerCase().trim()
      if (k && !m.has(k)) m.set(k, v)
    }
  }
  return m
}

const NL_COUNTRIES = new Set(['NL', 'NETHERLANDS', 'BE', 'BELGIUM'])
const NL_CITIES = new Set(['amsterdam', 'rotterdam', 'utrecht', 'eindhoven', 'groningen',
  'nijmegen', 'haarlem', 'tilburg', 'arnhem', 'maastricht'])

function venuePoints(venue: string, city: string, country: string, lookup: Map<string, NlVenue>): [number, boolean] {
  const vn = (venue ?? '').toLowerCase().trim()
  const cn = (city ?? '').toLowerCase().trim()
  const co = (country ?? '').toUpperCase().trim()
  const isAms = cn.includes('amsterdam')

  let best: NlVenue | null = null
  for (const [key, row] of lookup) {
    if (key && (key.includes(vn) || vn.includes(key))) {
      if (best === null || (row.tier ?? 3) < (best.tier ?? 3)) best = row
    }
  }
  if (best) {
    const t = best.tier ?? 3
    const pts = t === 1 ? 3.0 : t === 2 ? 2.0 : 1.0
    return [pts, (best.city ?? '').toLowerCase().includes('amsterdam')]
  }
  const isNL = NL_COUNTRIES.has(co) || NL_CITIES.has(cn)
  if (isNL) return [0.5, isAms]
  return [0.0, false]
}

function computeNlScore(
  raEvents: { venue?: string | null; city?: string | null; country?: string | null; date?: string | null }[],
  pfEvents: { venue?: string | null; city?: string | null; country?: string | null; start_date?: string | null }[],
  nlVenues: NlVenue[],
  instagramAudience: Record<string, unknown> | null,
  tiktokAudience: Record<string, unknown> | null,
): [number, NlScoreBreakdown] {
  const cutoff24m = new Date()
  cutoff24m.setDate(cutoff24m.getDate() - 730)
  const cutoffStr = cutoff24m.toISOString().slice(0, 10)

  const lookup = buildVenueLookup(nlVenues)
  const nlEvts = new Map<string, number>()
  const amsEvts = new Map<string, number>()

  for (const row of raEvents) {
    const date = (row.date ?? '').slice(0, 10)
    if (!date) continue
    const [pts, isAms] = venuePoints(row.venue ?? '', row.city ?? '', row.country ?? '', lookup)
    if (pts > 0) {
      const w = pts * (date >= cutoffStr ? 1.5 : 1.0)
      nlEvts.set(date, Math.max(nlEvts.get(date) ?? 0, w))
      if (isAms) amsEvts.set(date, Math.max(amsEvts.get(date) ?? 0, w))
    }
  }

  for (const e of pfEvents) {
    const date = (e.start_date ?? '').slice(0, 10)
    if (!date || nlEvts.has(date)) continue // RA takes priority for same date
    const [pts, isAms] = venuePoints(e.venue ?? '', e.city ?? '', e.country ?? '', lookup)
    if (pts > 0) {
      const w = pts * (date >= cutoffStr ? 1.5 : 1.0)
      nlEvts.set(date, w)
      if (isAms) amsEvts.set(date, Math.max(amsEvts.get(date) ?? 0, w))
    }
  }

  const amsTotal = [...amsEvts.values()].reduce((a, b) => a + b, 0)
  const nlTotal = [...nlEvts.values()].reduce((a, b) => a + b, 0)
  const amsScore = Math.min(100, (amsTotal / 12) * 100)
  const nlEventScore = Math.min(100, (nlTotal / 20) * 100)

  const igNl = extractCountryPct(instagramAudience, 'NL')
  const tkNl = extractCountryPct(tiktokAudience, 'NL')
  const demoVals = [igNl, tkNl].filter((v): v is number => v != null)
  const demoPct = demoVals.length > 0 ? demoVals.reduce((a, b) => a + b, 0) / demoVals.length : null

  let composite: number
  if (demoPct != null) {
    composite = 0.50 * Math.min(100, demoPct * 4.0) + 0.30 * amsScore + 0.20 * nlEventScore
  } else {
    composite = 0.65 * amsScore + 0.35 * nlEventScore
  }

  return [Math.round(composite), {
    nl_event_count: nlEvts.size,
    ams_event_count: amsEvts.size,
    ams_score: Math.round(amsScore),
    nl_event_score: Math.round(nlEventScore),
    demo_pct: demoPct,
    has_demographics: demoPct != null,
  }]
}

// ─── Scene Signal (port of _compute_scene_signal from lofi_pipeline.py) ───────

export interface SceneBreakdown {
  validation_score: number
  validation_hits: string[]
  nl_score: number
  ra_count: number
  ra_score: number
}

const SCENE_WEIGHTS: Record<string, number> = {
  first_ibiza: 25, first_boiler_room: 20, first_hor_berlin: 15,
  first_f2f_tv: 10, first_mixmag: 8,
  first_headline_500: 8, first_headline_1k: 12,
  first_headline_2k: 18, first_headline_5k: 25,
  first_tier_a_support: 12, beatport_top10: 10, beatport_number1: 15,
  first_extended_set: 6, first_all_night_long: 10, first_b2b: 4,
}

function computeSceneSignal(
  validationEvents: { event_type: string }[],
  nlScore: number,
  raEventCount: number,
): [number, SceneBreakdown] {
  let valPts = 0
  const valHits: string[] = []
  for (const row of validationEvents) {
    const et = row.event_type ?? ''
    valPts += SCENE_WEIGHTS[et] ?? 2
    if (et in SCENE_WEIGHTS) valHits.push(et)
  }
  const valScore = Math.min(100, valPts)
  const raScore = Math.min(100, raEventCount * 3)
  const scene = Math.round(0.40 * valScore + 0.35 * nlScore + 0.25 * raScore)
  return [scene, { validation_score: valScore, validation_hits: valHits.slice(0, 5), nl_score: nlScore, ra_count: raEventCount, ra_score: raScore }]
}

// Composite with weight redistribution when a component is null (matches Streamlit exactly)
function computeComposite(growthScore: number | null, sceneScore: number, lofiScore: number | null): number | null {
  const parts: [number | null, number][] = [[growthScore, 0.40], [sceneScore, 0.35], [lofiScore, 0.25]]
  const filled = parts.filter((p): p is [number, number] => p[0] != null)
  if (filled.length === 0) return null
  const wTotal = filled.reduce((s, [, w]) => s + w, 0)
  return Math.round(filled.reduce((s, [score, w]) => s + score * w, 0) / wTotal)
}

// ─── Route handler ─────────────────────────────────────────────────────────────

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  try {
    const supabase = createServiceClient()

    const [artistRes, raEventsRes, feedbackRes, notesRes, tracksRes, validationRes, playlistsRes, beatportRes, traxsourceRes, nlVenuesRes] = await Promise.all([
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
            cm_artist_rank, career_stage_score, career_trend_score, fan_base_rank,
            hometown_city, current_city, cm_timeseries, ml_features
          ),
          artist_ra (event_count, ra_slug, events),
          artist_partyflock (pf_fans, pf_total_performances, pf_upcoming_performances, pf_past_performances, pf_views, pf_genres, events),
          artist_lastfm (lfm_listeners, tags, similar_artists),
          xgboost_predictions (predicted_growth_90d, missing_pct),
          artist_ai_memo (*),
          artist_cm_extended (related_artists, urls, fan_cities, instagram_audience, tiktok_audience, albums, news, noteworthy_insights, milestones, youtube_audience, events_external, cm_stats)
        `)
        .eq('id', id)
        .single(),

      supabase
        .from('ra_events')
        .select('event_id, date, venue, city, country, venue_capacity, title, event_url, lineup, lineup_size')
        .eq('artist_id', id)
        .order('date', { ascending: false })
        .limit(100),

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

      supabase
        .from('artist_cm_tracks')
        .select('cm_track_id, track_name, release_date, spotify_streams, spotify_popularity, peak_spotify_chart, peak_beatport_chart, playlist_count')
        .eq('artist_id', id)
        .order('spotify_streams', { ascending: false, nullsFirst: false })
        .limit(20),

      supabase
        .from('validation_events')
        .select('id, event_type, event_date, source, confirmed, details')
        .eq('artist_id', id)
        .order('event_date', { ascending: false })
        .limit(30),

      supabase
        .from('artist_cm_playlists')
        .select('platform, playlist_name, playlist_followers, position, added_at')
        .eq('artist_id', id)
        .order('playlist_followers', { ascending: false, nullsFirst: false })
        .limit(30),

      supabase
        .from('beatport_chart_entries')
        .select('genre, chart_position, track_name, scraped_at')
        .eq('artist_id', id)
        .order('scraped_at', { ascending: false })
        .limit(20),

      supabase
        .from('traxsource_chart_entries')
        .select('genre, chart_position, track_name, scraped_at')
        .eq('artist_id', id)
        .order('scraped_at', { ascending: false })
        .limit(20),

      supabase
        .from('nl_venues')
        .select('id, venue_name, city, country, tier, ra_venue_name, pf_venue_name'),
    ])

    if (artistRes.error) throw artistRes.error
    const row = artistRes.data

    const cm = Array.isArray(row.artist_chartmetric) ? row.artist_chartmetric[0] : row.artist_chartmetric
    const ra = Array.isArray(row.artist_ra) ? row.artist_ra[0] : row.artist_ra
    const pf = Array.isArray(row.artist_partyflock) ? row.artist_partyflock[0] : row.artist_partyflock
    const lfm = Array.isArray(row.artist_lastfm) ? row.artist_lastfm[0] : row.artist_lastfm
    const xg = Array.isArray(row.xgboost_predictions) ? row.xgboost_predictions[0] : row.xgboost_predictions
    const memo = Array.isArray(row.artist_ai_memo) ? row.artist_ai_memo[0] : row.artist_ai_memo
    const ext = Array.isArray(row.artist_cm_extended) ? row.artist_cm_extended[0] : row.artist_cm_extended
    const lofi = row.lofi_feel as Record<string, unknown> | null
    const nlVenues = (nlVenuesRes.data ?? []) as NlVenue[]

    // Compute five scores
    const mlFeatures = (cm?.ml_features as MlFeaturesForScoring | null) ?? null
    const fiveScores = mlFeatures ? computeFiveScores(cm ?? {}, mlFeatures) : null

    // Compute NL score
    const pfEventsArr = ((pf as Record<string, unknown> | null)?.events as Record<string, unknown>[] | null) ?? []
    const [nlScore, nlScoreBreakdown] = computeNlScore(
      (raEventsRes.data ?? []) as { venue?: string | null; city?: string | null; country?: string | null; date?: string | null }[],
      pfEventsArr as { venue?: string | null; city?: string | null; country?: string | null; start_date?: string | null }[],
      nlVenues,
      (ext?.instagram_audience as Record<string, unknown> | null) ?? null,
      (ext?.tiktok_audience as Record<string, unknown> | null) ?? null,
    )

    // Compute scene signal (exact port of _compute_scene_signal)
    const validationEventsArr = (validationRes.data ?? []) as ValidationEventRow[]
    const raEventCount = ra?.event_count ?? 0
    const [sceneScore, sceneBreakdown] = computeSceneSignal(validationEventsArr, nlScore, raEventCount)

    // Compute growth score: clamp(50 + predicted_growth_90d, 0, 100)
    const predictedGrowth = xg?.predicted_growth_90d ?? null
    const growthScore = predictedGrowth != null ? Math.round(Math.max(0, Math.min(100, 50 + predictedGrowth))) : null

    // Compute LOFI fit score
    const lofiScore = lofi ? ((lofi as { score?: number }).score ?? null) : null

    // Composite with weight redistribution when component is null
    const compositeScore = computeComposite(growthScore, sceneScore, lofiScore)

    // Extract timeseries
    let timeseries: TimeseriesPoint[] | null = null
    const multiTimeseries: MultiTimeseriesItem[] = []

    if (cm?.cm_timeseries) {
      const ts = cm.cm_timeseries as Record<string, Record<string, { date: string; value: number }[]>>
      const cutoff = new Date()
      cutoff.setFullYear(cutoff.getFullYear() - 1)
      const cutoffStr = cutoff.toISOString().slice(0, 10)

      const extractPlatform = (pts: { date: string; value: number }[] | undefined) =>
        (pts ?? []).filter(p => p.date >= cutoffStr).filter((_, i) => i % 7 === 0)

      const spotifyPts = extractPlatform(ts?.spotify?.listeners)
      const igPts = extractPlatform(ts?.instagram?.followers)
      const tiktokPts = extractPlatform(ts?.tiktok?.followers)
      const scPts = extractPlatform(ts?.soundcloud?.followers)

      timeseries = spotifyPts.map(p => ({ date: p.date, listeners: p.value }))

      if (spotifyPts.length) multiTimeseries.push({ platform: 'spotify', label: 'Spotify Listeners', data: spotifyPts })
      if (igPts.length) multiTimeseries.push({ platform: 'instagram', label: 'Instagram Followers', data: igPts })
      if (tiktokPts.length) multiTimeseries.push({ platform: 'tiktok', label: 'TikTok Followers', data: tiktokPts })
      if (scPts.length) multiTimeseries.push({ platform: 'soundcloud', label: 'SoundCloud Followers', data: scPts })
    }

    // Similar artists: LFM first (preserves order), then CM
    const similarArtists: string[] = [
      ...((lfm?.similar_artists as string[] | null) ?? []),
      ...((ext?.related_artists as { name: string }[] | null)?.map(a => a.name) ?? []),
    ].filter((v, i, arr) => arr.indexOf(v) === i).slice(0, 15)

    // RA fallback: if ra_events table is empty, try artist_ra.events JSONB
    let raEventsData = (raEventsRes.data ?? []) as RaEventSummary[]
    if (raEventsData.length === 0 && ra) {
      const jsonbEvents = (ra as Record<string, unknown>).events as Record<string, unknown>[] | null
      if (Array.isArray(jsonbEvents)) {
        raEventsData = jsonbEvents.map((e) => ({
          event_id: String(e.event_id ?? e.id ?? ''),
          date: String(e.date ?? ''),
          title: (e.title as string | null) ?? null,
          event_url: (e.event_url as string | null) ?? (e.url as string | null) ?? null,
          venue: String(e.venue ?? ''),
          city: (e.city as string | null) ?? null,
          country: (e.country as string | null) ?? null,
          venue_capacity: (e.venue_capacity as number | null) ?? null,
        })) as RaEventSummary[]
      }
    }

    const tracks: TrackRow[] = (tracksRes.data ?? []) as TrackRow[]

    const detail: ArtistDetail = {
      id: row.id,
      name: row.name,
      slug: row.slug,
      status: row.candidate_status as ArtistDetail['status'],
      imageUrl: cm?.image_url ?? null,
      coverUrl: cm?.cover_url ?? null,
      genres: cm?.genres ?? null,
      description: decodeHtmlEntities(cm?.description ?? null),
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
      lofiFeel: lofi ? (lofi as unknown as ArtistDetail['lofiFeel']) : null,
      pfFans: pf?.pf_fans ?? null,
      pfTotalPerformances: pf?.pf_total_performances ?? null,
      pfUpcomingPerformances: pf?.pf_upcoming_performances ?? null,
      pfPastPerformances: pf?.pf_past_performances ?? null,
      pfViews: pf?.pf_views ?? null,
      pfGenres: pf?.pf_genres ?? null,
      lfmListeners: lfm?.lfm_listeners ?? null,
      lfmTags: lfm?.tags ?? null,
      raEventCount: ra?.event_count ?? null,
      xgboostGrowth90d: xg?.predicted_growth_90d ?? null,
      missingDataPct: xg?.missing_pct ?? null,
      bookedSimilarCount: row.booked_similar_count,
      bookedNeighborCount: row.booked_neighbor_count,
      timeseries,
      multiTimeseries,
      raEvents: raEventsData,
      feedback: feedbackRes.data ?? [],
      artistNotes: (notesRes.data ?? []).map((n: Record<string, unknown>) => ({
        id: String(n.id),
        text: String(n.text ?? ''),
        created_at: String(n.created_at ?? ''),
      })).filter((n: { text: string }) => n.text),
      aiMemo: memo ?? null,
      updatedAt: row.updated_at ?? null,
      tracks,
      validationEvents: validationEventsArr,
      similarArtists,
      socialLinks: (ext?.urls as { url: string[]; domain: string }[] | null) ?? [],
      fanCities: (ext?.fan_cities as { city: string; country: string; count?: number; pct?: number }[] | null) ?? [],
      instagramAudience: (ext?.instagram_audience as Record<string, unknown> | null) ?? null,
      albums: (ext?.albums as { name: string; release_date?: string; image_url?: string; type?: string }[] | null) ?? [],
      noteworthy: (ext?.noteworthy_insights as { title?: string; description?: string; value?: string }[] | null) ?? [],
      cmArtistRank: cm?.cm_artist_rank ?? null,
      fiveScores,
      mlFeatures: mlFeatures ? Object.fromEntries(Object.entries(mlFeatures).filter(([, v]) => v !== undefined)) as Record<string, number | null> : null,
      playlists: (playlistsRes.data ?? []) as { platform: string; playlist_name: string; playlist_followers: number | null; position: number | null; added_at: string | null }[],
      beatportChartEntries: (beatportRes.data ?? []) as { genre: string | null; chart_position: number | null; track_name: string | null; scraped_at: string }[],
      traxsourceChartEntries: (traxsourceRes.data ?? []) as { genre: string | null; chart_position: number | null; track_name: string | null; scraped_at: string | null }[],
      pfEvents: pfEventsArr,
      tiktokAudience: (ext?.tiktok_audience as Record<string, unknown> | null) ?? null,
      milestones: (ext?.milestones as Record<string, unknown>[] | null) ?? null,
      youtubeAudience: (ext?.youtube_audience as Record<string, unknown> | null) ?? null,
      eventsExternal: (ext?.events_external as Record<string, unknown>[] | null) ?? null,
      cmStats: (ext?.cm_stats as Record<string, unknown> | null) ?? null,
      // Computed booking signals (server-side, exact match with Streamlit formulas)
      nlScore,
      nlScoreBreakdown,
      sceneScore,
      sceneBreakdown,
      growthScore,
      compositeScore,
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
    const allowed = ['candidate_status', 'excluded', 'excluded_reason']
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
