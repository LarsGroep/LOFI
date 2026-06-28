import { NextResponse } from 'next/server'
import Anthropic from '@anthropic-ai/sdk'
import { createServiceClient } from '@/lib/supabase/server'

function getAnthropicClient(): Anthropic | null {
  const key = process.env.ANTHROPIC_API_KEY?.trim()
  return key ? new Anthropic({ apiKey: key }) : null
}

function aiFailure(err: unknown): { message: string; status: number } {
  const raw = err instanceof Error ? err.message : String(err)
  const lower = raw.toLowerCase()
  if (lower.includes('credit') || lower.includes('quota') || lower.includes('billing') || lower.includes('insufficient')) {
    return {
      status: 402,
      message: 'Anthropic credits or billing are exhausted. Add API credits/billing in Anthropic, then regenerate the memo.',
    }
  }
  if (lower.includes('api key') || lower.includes('unauthorized') || lower.includes('authentication')) {
    return {
      status: 401,
      message: 'Anthropic API key is missing or invalid in Vercel environment variables.',
    }
  }
  return {
    status: 503,
    message: 'AI memo generation is temporarily unavailable. The structured artist data is still usable.',
  }
}

function fmt(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return 'N/A'
  if (n >= 999_500) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}K`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(Math.round(n))
}

export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  try {
    const supabase = createServiceClient()

    // Fetch all data needed for the memo
    const [artistRes, notesRes] = await Promise.all([
      supabase
        .from('artists')
        .select(`
          id, name, slug, candidate_status, lofi_feel,
          booked_similar_count, booked_neighbor_count,
          artist_chartmetric (
            description, career_status, record_label, booking_agent, genres,
            sp_monthly_listeners, sp_followers, ig_followers, tiktok_followers,
            yt_subscribers, soundcloud_followers, cpp_score, cm_artist_score,
            career_stage_score, career_trend_score, hometown_city, current_city,
            cm_timeseries
          ),
          artist_ra (event_count, events),
          artist_partyflock (pf_fans, pf_total_performances, pf_upcoming_performances, pf_genres),
          artist_lastfm (lfm_listeners, tags, similar_artists),
          xgboost_predictions (predicted_growth_90d, missing_pct, available_features, total_features),
          artist_cm_extended (noteworthy_insights, milestones, related_artists, fan_cities)
        `)
        .eq('id', id)
        .single(),
      supabase
        .from('artist_notes')
        .select('note_type, text, author, created_at')
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
    const ext = Array.isArray(row.artist_cm_extended) ? row.artist_cm_extended[0] : row.artist_cm_extended
    const lofi = row.lofi_feel as Record<string, unknown> | null
    const notes = notesRes.data ?? []
    const milestones = (ext?.milestones as unknown[] | null) ?? []

    // Compute 30d Spotify listener delta
    let sp30dDelta: string = 'N/A'
    try {
      const ts = cm?.cm_timeseries as Record<string, Record<string, { date: string; value: number }[]>> | null
      const pts = ts?.spotify?.listeners
      if (pts?.length) {
        const sorted = [...pts].sort((a, b) => a.date.localeCompare(b.date))
        const latest = sorted[sorted.length - 1].value
        const cutoff = new Date(sorted[sorted.length - 1].date)
        cutoff.setDate(cutoff.getDate() - 30)
        const cutoffStr = cutoff.toISOString().slice(0, 10)
        const old = sorted.find(p => p.date >= cutoffStr)
        if (old && old.value > 0) {
          const pct = ((latest - old.value) / old.value) * 100
          sp30dDelta = `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`
        }
      }
    } catch { /* ignore */ }

    // Data freshness: check if chartmetric data is recent
    const cmUpdatedAt = (cm as unknown as { updated_at?: string })?.updated_at
    const daysSinceUpdate = cmUpdatedAt
      ? (Date.now() - new Date(cmUpdatedAt).getTime()) / 86_400_000
      : 999
    const dataFreshness = daysSinceUpdate < 2 ? 'Fresh' : daysSinceUpdate < 7 ? 'Partial' : 'Stale'

    // Fetch LOFI sound framework benchmarks matching this artist's genres
    const artistGenres = (cm?.genres ?? []).map((g: string) => g.toLowerCase())
    const { data: frameworkData } = await supabase
      .from('lofi_sound_framework')
      .select('sound, tier, bucket, artists (name)')

    const soundFrameworkSection = (() => {
      if (!frameworkData?.length) return 'No sound framework configured yet.'
      // Group by sound, find sounds that overlap with artist genres
      const sounds = new Map<string, { tier: string; name: string; bucket: string }[]>()
      for (const entry of frameworkData) {
        const artistEntry = Array.isArray(entry.artists) ? entry.artists[0] : entry.artists
        if (!artistEntry) continue
        if (!sounds.has(entry.sound)) sounds.set(entry.sound, [])
        sounds.get(entry.sound)!.push({ tier: entry.tier, name: artistEntry.name, bucket: entry.bucket })
      }
      // Prioritise sounds that match artist genres, then include all
      const relevantSounds: string[] = []
      const otherSounds: string[] = []
      for (const [sound] of sounds) {
        const soundLower = sound.toLowerCase()
        const matches = artistGenres.some((g: string) => soundLower.includes(g) || g.includes(soundLower.split(' ')[0]))
        if (matches) relevantSounds.push(sound)
        else otherSounds.push(sound)
      }
      const orderedSounds = [...relevantSounds, ...otherSounds].slice(0, 4)
      const lines = orderedSounds.map(sound => {
        const artists = sounds.get(sound)!
        const byTier = ['A+', 'A', 'B', 'Watch'].map(tier => {
          const names = artists.filter(a => a.tier === tier).map(a => a.name)
          return names.length ? `${tier}: ${names.join(', ')}` : null
        }).filter(Boolean)
        return `${sound}: ${byTier.join(' | ')}`
      })
      const matchNote = relevantSounds.length > 0 ? ` (${relevantSounds.join(', ')} appear relevant for this artist)` : ''
      return lines.join('\n') + matchNote
    })()

    // Build booker notes section
    const notesSection = notes.length
      ? notes.map((n: any) => `[${n.note_type.toUpperCase()}] ${n.text} (by ${n.author})`).join('\n')
      : 'No booker notes.'

    // Build LOFI Fit section
    const lofiFitSection = lofi
      ? [
          `Score: ${lofi.score ?? 'N/A'}/100`,
          lofi.reason ? `Reason: ${lofi.reason}` : '',
          lofi.green_flags ? `Green flags: ${(lofi.green_flags as string[]).join(', ')}` : '',
          lofi.red_flags ? `Red flags: ${(lofi.red_flags as string[]).join(', ')}` : '',
        ].filter(Boolean).join('\n')
      : 'No LOFI fit data.'

    const prompt = `You are an expert music booking analyst for LOFI Amsterdam, a leading electronic music venue and promotion company. Your job is to evaluate whether an artist is worth booking for LOFI events.

ARTIST DATA:
Name: ${row.name}
Status: ${row.candidate_status}
Genres: ${cm?.genres?.join(', ') ?? 'Unknown'}
Career stage: ${cm?.career_status ?? 'Unknown'}
Based: ${cm?.current_city ?? cm?.hometown_city ?? 'Unknown'}
Label: ${cm?.record_label ?? 'Unknown'}
Agent: ${cm?.booking_agent ?? 'Unknown'}
Description: ${cm?.description?.slice(0, 500) ?? 'No bio available'}

STREAMING & SOCIAL METRICS:
Spotify monthly listeners: ${fmt(cm?.sp_monthly_listeners)}
Spotify 30-day change: ${sp30dDelta}
Spotify followers: ${fmt(cm?.sp_followers)}
Instagram followers: ${fmt(cm?.ig_followers)}
TikTok followers: ${fmt(cm?.tiktok_followers)}
YouTube subscribers: ${fmt(cm?.yt_subscribers)}
SoundCloud followers: ${fmt(cm?.soundcloud_followers)}
Chartmetric artist score: ${cm?.cm_artist_score?.toFixed(1) ?? 'N/A'}
CPP score: ${cm?.cpp_score?.toFixed(1) ?? 'N/A'}
Career stage score: ${cm?.career_stage_score?.toFixed(1) ?? 'N/A'} (career trend: ${cm?.career_trend_score?.toFixed(1) ?? 'N/A'})

LAST.FM:
Listeners: ${fmt(lfm?.lfm_listeners)}
Tags: ${lfm?.tags?.slice(0, 8).join(', ') ?? 'None'}
Similar artists: ${lfm?.similar_artists?.slice(0, 5).join(', ') ?? 'None'}

RESIDENT ADVISOR:
Total events tracked: ${ra?.event_count ?? 0}
Recent events: ${JSON.stringify((ra?.events as unknown[])?.slice(0, 5) ?? [])}

PARTYFLOCK (NL market):
Fans: ${fmt(pf?.pf_fans)}
Total NL performances: ${pf?.pf_total_performances ?? 0}
Upcoming NL performances: ${pf?.pf_upcoming_performances ?? 0}
NL genres listed: ${pf?.pf_genres?.join(', ') ?? 'None'}

LOFI FIT ASSESSMENT:
${lofiFitSection}

LOFI NETWORK SIGNALS:
Artists in LOFI's booked roster who list this artist as similar: ${row.booked_similar_count}
Artists in LOFI's booked roster who are career-stage neighbors: ${row.booked_neighbor_count}

ML PREDICTION (XGBoost):
Predicted CPP score growth in next 90 days: ${xg?.predicted_growth_90d != null ? `${(xg.predicted_growth_90d).toFixed(1)}%` : 'N/A'}
Data coverage: ${xg?.available_features ?? 'N/A'} / ${xg?.total_features ?? 'N/A'} features

NOTEWORTHY INSIGHTS (from Chartmetric):
${JSON.stringify((ext?.noteworthy_insights as unknown[])?.slice(0, 3) ?? [], null, 2)}

MILESTONES WITH SOURCES:
${JSON.stringify(milestones.slice(0, 8), null, 2)}

LOFI SOUND FRAMEWORK — BENCHMARK ARTISTS (curated by LOFI team):
${soundFrameworkSection}

BOOKER NOTES FROM LOFI TEAM:
${notesSection}

---

Based on all this data, generate a booking assessment for LOFI Amsterdam. LOFI books electronic music for Amsterdam shows — primarily tech-house, house, and related underground genres. The ideal booking is an artist who:
- Has strong NL/European electronic scene presence
- Shows growth acceleration (not just size)
- Fits the LOFI sound profile (underground but festival-capable)
- Has credibility signals (agency tier, label, festival bookings)

IMPORTANT SCORING CONTEXT:
- XGBoost predicts Chartmetric CPP score growth over the next 90 days. Do not describe it as a Spotify listener forecast.
- Booking urgency is separate from LOFI fit. A fast-growing artist can still be a weak LOFI fit; a perfect LOFI fit can still be low urgency.
- Booking signal weights are Trend Forecast 40%, Scene Evidence 35%, LOFI Fit 25%.
- Explain every verdict in plain language for non-technical bookers. Use milestone source/date fields when referencing achievements.
- When suggesting comparable artists in "comparable_past", ONLY reference artists from the LOFI Sound Framework above. These are the benchmark artists LOFI has curated as examples of success in each sound. Do not invent comparables — if no framework artist is a good match, leave comparable_past empty.

Return ONLY valid JSON matching this exact structure (no markdown, no explanation):
{
  "verdict": "Book Now" | "Strong Watch" | "Monitor" | "Pass",
  "verdict_reason": "One clear sentence explaining the verdict",
  "summary": "2-3 natural language sentences explaining the artist's current position and trajectory for a non-technical booker",
  "signals": [
    { "label": "Momentum", "rating": "Very Strong" | "Strong" | "Moderate" | "Weak" | "Insufficient Data", "detail": "One sentence" },
    { "label": "Scene Credibility", "rating": "...", "detail": "..." },
    { "label": "LOFI Fit", "rating": "...", "detail": "..." }
  ],
  "opportunities": ["bullet 1", "bullet 2"],
  "risks": ["bullet 1", "bullet 2"],
  "comparable_past": ["Only use artist names from the LOFI Sound Framework above"]
}`

    let memoText: string

    try {
      const anthropic = getAnthropicClient()
      if (!anthropic) {
        return NextResponse.json({ error: 'Anthropic API key is missing in Vercel environment variables.' }, { status: 401 })
      }
      const message = await anthropic.messages.create({
        model: 'claude-sonnet-4-6',
        max_tokens: 1024,
        messages: [{ role: 'user', content: prompt }],
      })
      const content = message.content[0]
      if (content.type !== 'text') throw new Error('Unexpected response type from Claude')
      memoText = content.text
    } catch (claudeErr) {
      console.warn('[memo] Claude failed, trying Ollama fallback:', claudeErr)
      const ollamaUrl = process.env.OLLAMA_BASE_URL ?? 'http://localhost:11434'
      const ollamaModel = process.env.OLLAMA_MODEL ?? 'llama3.1'
      try {
        const ollamaRes = await fetch(`${ollamaUrl}/v1/chat/completions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: ollamaModel,
            messages: [{ role: 'user', content: prompt }],
            stream: false,
          }),
          signal: AbortSignal.timeout(60_000),
        })
        if (!ollamaRes.ok) throw new Error(`Ollama ${ollamaRes.status}`)
        const ollamaData = await ollamaRes.json()
        memoText = ollamaData.choices?.[0]?.message?.content ?? ''
        if (!memoText) throw new Error('Empty Ollama response')
      } catch (ollamaErr) {
        console.error('[memo] Ollama fallback also failed:', ollamaErr)
        throw claudeErr // re-throw original error
      }
    }

    const memo = JSON.parse(memoText)

    // Upsert into DB
    const { error: upsertError } = await supabase
      .from('artist_ai_memo')
      .upsert({
        artist_id: id,
        verdict: memo.verdict,
        verdict_reason: memo.verdict_reason,
        summary: memo.summary,
        signals: memo.signals,
        opportunities: memo.opportunities,
        risks: memo.risks,
        comparable_past: memo.comparable_past ?? [],
        data_freshness: dataFreshness,
        generated_at: new Date().toISOString(),
        model_version: 'claude-sonnet-4-6',
      })

    if (upsertError) console.error('[memo upsert]', upsertError)

    // Mark notes as used in memo
    if (notes.length > 0) {
      await supabase
        .from('artist_notes')
        .update({ used_in_memo: true })
        .eq('artist_id', id)
    }

    // Auto-schedule for deletion if artist is clearly outside LOFI's target cohort.
    // Condition: Pass verdict + no NL presence + no RA events + signals all Weak/Insufficient
    const autoDeleteCandidate = (
      memo.verdict === 'Pass' &&
      (ra?.event_count ?? 0) === 0 &&
      (pf?.pf_fans ?? 0) === 0 &&
      (memo.signals ?? []).every((s: { rating: string }) => ['Weak', 'Insufficient Data'].includes(s.rating))
    )
    if (autoDeleteCandidate) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (supabase as any)
        .from('artists')
        .update({
          scheduled_delete: true,
          scheduled_delete_reason: `Auto: AI verdict "Pass" — all signals Weak/Insufficient, no RA or NL presence`,
        })
        .eq('id', id)
      console.log(`[memo] Auto-scheduled ${row.name} (${id}) for deletion — far outlier from LOFI cohort`)
    }

    return NextResponse.json({ ...memo, data_freshness: dataFreshness, generated_at: new Date().toISOString(), autoScheduledDelete: autoDeleteCandidate })
  } catch (err) {
    console.error('[POST /api/artists/[id]/memo]', err)
    const failure = aiFailure(err)
    return NextResponse.json({ error: failure.message }, { status: failure.status })
  }
}
