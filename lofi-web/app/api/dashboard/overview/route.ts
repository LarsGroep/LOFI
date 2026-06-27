import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET() {
  try {
    const supabase = createServiceClient()

    const [milestonesRes, youtubeRes] = await Promise.all([
      supabase
        .from('validation_events')
        .select(`
          id, event_type, event_date, source, confirmed,
          artists (id, name,
            artist_chartmetric (image_url)
          )
        `)
        .lte('event_date', new Date().toISOString().slice(0, 10))
        .order('detected_at', { ascending: false })
        .limit(8),

      supabase
        .from('youtube_sets')
        .select('video_id, title, thumbnail_url, view_count, view_velocity, matched_artist_names, published_at, is_trending')
        .eq('is_trending', true)
        .order('view_velocity', { ascending: false, nullsFirst: false })
        .limit(8),
    ])

    const milestones = (milestonesRes.data ?? []).map(m => {
      const artist = Array.isArray(m.artists) ? m.artists[0] : m.artists
      const cm = Array.isArray(artist?.artist_chartmetric) ? artist.artist_chartmetric[0] : artist?.artist_chartmetric
      return {
        id: m.id,
        eventType: m.event_type,
        eventDate: m.event_date,
        source: m.source,
        confirmed: m.confirmed,
        artistId: artist?.id ?? null,
        artistName: artist?.name ?? 'Unknown',
        imageUrl: cm?.image_url ?? null,
      }
    })

    return NextResponse.json({
      milestones,
      trendingYoutube: youtubeRes.data ?? [],
    })
  } catch (err) {
    console.error('[GET /api/dashboard/overview]', err)
    return NextResponse.json({ error: 'Failed to fetch overview' }, { status: 500 })
  }
}
