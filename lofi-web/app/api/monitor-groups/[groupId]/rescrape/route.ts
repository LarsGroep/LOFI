import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

const CM_BASE = 'https://api.chartmetric.com/api'

async function getCmToken(): Promise<string | null> {
  const rt = process.env.CHARTMETRIC_REFRESH_TOKEN?.trim()
  if (!rt) return null
  try {
    const res = await fetch(`${CM_BASE}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refreshtoken: rt }),
    })
    if (!res.ok) return null
    const data = await res.json()
    return data.token ?? null
  } catch { return null }
}

// Search CM by name → return { cm_id, name }
async function cmSearchByName(token: string, name: string): Promise<number | null> {
  try {
    const res = await fetch(`${CM_BASE}/search?q=${encodeURIComponent(name)}&type=artists&limit=1`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return null
    const data = await res.json()
    const artists = data?.obj?.artists ?? []
    return artists[0]?.id ?? null
  } catch { return null }
}

// Fetch full artist profile from CM → normalize to our DB field names
async function cmGetArtist(token: string, cmId: number): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${CM_BASE}/artist/${cmId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return null
    const data = await res.json()
    const p = data?.obj
    if (!p) return null
    return {
      cm_artist_id:        cmId,
      cm_artist_score:     p.cm_score ?? null,
      cm_artist_rank:      p.cm_score_rank ?? null,
      sp_monthly_listeners:p.spotify_monthly_listeners ?? null,
      sp_followers:        p.spotify_followers ?? null,
      sp_popularity:       p.spotify_popularity ?? null,
      ig_followers:        p.instagram_followers ?? null,
      tiktok_followers:    p.tiktok_followers ?? null,
      yt_subscribers:      p.youtube_channel_subscribers ?? null,
      soundcloud_followers:p.soundcloud_followers ?? null,
      cpp_score:           p.cpp ?? null,
      cpp_rank:            p.cpp_rank ?? null,
      career_status:       p.career_status ?? null,
      career_stage_score:  p.career_stage_score ?? null,
      career_trend_score:  p.career_trend_score ?? null,
      fan_base_rank:       p.fan_base_rank ?? null,
      record_label:        p.record_label ?? null,
      booking_agent:       p.booking_agent ?? null,
      updated_at:          new Date().toISOString(),
    }
  } catch { return null }
}

// POST /api/monitor-groups/[groupId]/rescrape
export async function POST(req: Request, { params }: { params: Promise<{ groupId: string }> }) {
  const { groupId } = await params
  const supabase = createServiceClient()
  const origin = new URL(req.url).origin

  try {
    // Get all artists in the group
    const { data: members, error: membersErr } = await supabase
      .from('monitor_group_members')
      .select('artist_id, artists(id, name)')
      .eq('group_id', groupId)
    if (membersErr) throw membersErr
    if (!members?.length) return NextResponse.json({ ok: true, updated: 0, message: 'No artists in group' })

    const token = await getCmToken()
    if (!token) return NextResponse.json({ error: 'Chartmetric not configured — set CHARTMETRIC_REFRESH_TOKEN' }, { status: 503 })

    const results: { name: string; ok: boolean; reason?: string }[] = []

    for (const member of members as any[]) {
      const artist = Array.isArray(member.artists) ? member.artists[0] : member.artists
      if (!artist) continue

      const artistName: string = (artist as { name: string }).name

      try {
        // 1. Get stored CM ID (if any)
        const { data: existingCm } = await supabase
          .from('artist_chartmetric')
          .select('cm_artist_id')
          .eq('artist_id', member.artist_id)
          .single()

        let cmId: number | null = (existingCm as { cm_artist_id: number | null } | null)?.cm_artist_id ?? null

        // 2. If no CM ID stored, search by name
        if (!cmId) {
          cmId = await cmSearchByName(token, artistName)
          if (!cmId) {
            results.push({ name: artistName, ok: false, reason: 'Not found on Chartmetric' })
            continue
          }
        }

        // 3. Fetch fresh profile
        const fresh = await cmGetArtist(token, cmId)
        if (!fresh) {
          results.push({ name: artistName, ok: false, reason: 'CM API error' })
          continue
        }

        // 4. Upsert into artist_chartmetric
        await supabase
          .from('artist_chartmetric')
          .upsert({ artist_id: member.artist_id, ...fresh })

        // 5. Recompute five scores from updated data
        await fetch(`${origin}/api/artists/${member.artist_id}/refresh`, {
          method: 'POST',
        }).catch(() => null) // non-blocking: score refresh is best-effort

        results.push({ name: artistName, ok: true })
        // Small delay to stay within CM rate limit (1 req/sec)
        await new Promise(r => setTimeout(r, 1200))
      } catch (err) {
        results.push({ name: artistName, ok: false, reason: String(err) })
      }
    }

    // Update last_scraped_at on the group
    await supabase
      .from('monitor_groups')
      .update({ last_scraped_at: new Date().toISOString() })
      .eq('id', groupId)

    const updated = results.filter(r => r.ok).length
    return NextResponse.json({ ok: true, updated, total: results.length, results })
  } catch (err) {
    console.error('[POST /api/monitor-groups/[groupId]/rescrape]', err)
    return NextResponse.json({ error: 'Rescrape failed' }, { status: 500 })
  }
}

// PATCH /api/monitor-groups/[groupId]/rescrape — update interval setting
export async function PATCH(req: Request, { params }: { params: Promise<{ groupId: string }> }) {
  const { groupId } = await params
  const { interval_hours } = await req.json()
  const supabase = createServiceClient()
  try {
    await supabase
      .from('monitor_groups')
      .update({ rescrape_interval_hours: interval_hours ?? null })
      .eq('id', groupId)
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('[PATCH /api/monitor-groups/[groupId]/rescrape]', err)
    return NextResponse.json({ error: 'Failed to set interval' }, { status: 500 })
  }
}
