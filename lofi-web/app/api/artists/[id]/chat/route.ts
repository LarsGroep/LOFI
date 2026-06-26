import Anthropic from '@anthropic-ai/sdk'
import { createServiceClient } from '@/lib/supabase/server'

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY! })

function fmt(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return 'N/A'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(Math.round(n))
}

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const { message, history = [] } = await req.json() as {
    message: string
    history: { role: 'user' | 'assistant'; content: string }[]
  }

  const supabase = createServiceClient()

  const [artistRes, memoRes] = await Promise.all([
    supabase
      .from('artists')
      .select(`
        id, name, candidate_status, lofi_feel,
        artist_chartmetric (
          genres, sp_monthly_listeners, ig_followers,
          record_label, booking_agent, career_status, current_city
        ),
        artist_ra (event_count),
        artist_lastfm (lfm_listeners, tags, similar_artists),
        xgboost_predictions (predicted_growth_90d),
        artist_cm_extended (milestones)
      `)
      .eq('id', id)
      .single(),
    supabase
      .from('artist_ai_memo')
      .select('verdict, verdict_reason, summary')
      .eq('artist_id', id)
      .maybeSingle(),
  ])

  if (artistRes.error) {
    return new Response('Artist not found', { status: 404 })
  }

  const row = artistRes.data
  const cm = Array.isArray(row.artist_chartmetric) ? row.artist_chartmetric[0] : row.artist_chartmetric
  const ra = Array.isArray(row.artist_ra) ? row.artist_ra[0] : row.artist_ra
  const lfm = Array.isArray(row.artist_lastfm) ? row.artist_lastfm[0] : row.artist_lastfm
  const xg = Array.isArray(row.xgboost_predictions) ? row.xgboost_predictions[0] : row.xgboost_predictions
  const ext = Array.isArray(row.artist_cm_extended) ? row.artist_cm_extended[0] : row.artist_cm_extended
  const lofi = row.lofi_feel as Record<string, unknown> | null
  const memo = memoRes.data

  const systemPrompt = `You are a booking intelligence assistant for LOFI Amsterdam, an underground electronic music venue and promoter. You help the booking team make decisions about artists.

ARTIST BRIEF — ${row.name}:
Status: ${row.candidate_status}
Genres: ${cm?.genres?.slice(0, 5).join(', ') ?? 'Unknown'}
Career stage: ${cm?.career_status ?? 'Unknown'}
Based: ${cm?.current_city ?? 'Unknown'}
Label: ${cm?.record_label ?? 'None'}
Agent: ${cm?.booking_agent ?? 'None'}
Spotify listeners: ${fmt(cm?.sp_monthly_listeners)}
Instagram: ${fmt(cm?.ig_followers)} followers
Last.fm listeners: ${fmt(lfm?.lfm_listeners)}
Last.fm tags: ${lfm?.tags?.slice(0, 6).join(', ') ?? 'None'}
Similar artists: ${lfm?.similar_artists?.slice(0, 4).join(', ') ?? 'None'}
RA events tracked: ${ra?.event_count ?? 0}
XGBoost 90d CPP growth prediction: ${xg?.predicted_growth_90d != null ? `${(xg.predicted_growth_90d).toFixed(1)}%` : 'N/A'}
LOFI fit score: ${lofi?.score != null ? `${Math.round(lofi.score as number)}/100` : 'N/A'}
${lofi?.matched ? `Matched signals: ${JSON.stringify(lofi.matched)}` : ''}
${lofi?.disqualified ? 'DISQUALIFIED by genre filter' : ''}
Recent milestones: ${JSON.stringify((ext?.milestones as unknown[])?.slice(0, 3) ?? [])}
${memo ? `\nEXISTING AI ASSESSMENT:\nVerdict: ${memo.verdict} — ${memo.verdict_reason}\nSummary: ${memo.summary}` : ''}

You have expert knowledge of the underground electronic music scene, particularly tech-house, house, techno, and related genres. LOFI books artists for Amsterdam shows, typically 300–2000 capacity. Answer concisely and from the perspective of an experienced booking advisor. If the question is about data you don't have, say so honestly.`

  const stream = await anthropic.messages.stream({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 512,
    system: systemPrompt,
    messages: [
      ...history.slice(-8),
      { role: 'user', content: message },
    ],
  })

  const readable = new ReadableStream({
    async start(controller) {
      for await (const chunk of stream) {
        if (
          chunk.type === 'content_block_delta' &&
          chunk.delta.type === 'text_delta'
        ) {
          controller.enqueue(new TextEncoder().encode(chunk.delta.text))
        }
      }
      controller.close()
    },
    cancel() {
      stream.controller.abort()
    },
  })

  return new Response(readable, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Transfer-Encoding': 'chunked',
      'X-Accel-Buffering': 'no',
    },
  })
}
