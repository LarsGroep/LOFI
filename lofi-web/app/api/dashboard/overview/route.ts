import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET() {
  try {
    const supabase = createServiceClient()
    const today = new Date().toISOString().slice(0, 10)
    const in14days = new Date(Date.now() + 14 * 86400_000).toISOString().slice(0, 10)

    const [milestonesRes, youtubeRes, upcomingRes] = await Promise.all([
      supabase
        .from('validation_events')
        .select(`
          id, event_type, event_date, source, confirmed,
          artists (id, name,
            artist_chartmetric (image_url)
          )
        `)
        .lte('event_date', today)
        .order('detected_at', { ascending: false })
        .limit(8),

      supabase
        .from('youtube_sets')
        .select('video_id, title, thumbnail_url, view_count, view_velocity, matched_artist_names, published_at, is_trending')
        .eq('is_trending', true)
        .order('view_velocity', { ascending: false, nullsFirst: false })
        .limit(8),

      supabase
        .from('ra_events')
        .select('artist_id, artist_name, date, venue, city, country, artists(id, artist_chartmetric(image_url))')
        .gte('date', today)
        .lte('date', in14days)
        .order('date', { ascending: true })
        .limit(20),
    ])

    const milestones = (milestonesRes.data ?? []).map((m: any) => {
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

    const upcomingEvents = (upcomingRes.data ?? []).map((e: any) => {
      const artist = Array.isArray(e.artists) ? e.artists[0] : e.artists
      const cm = Array.isArray(artist?.artist_chartmetric) ? artist.artist_chartmetric[0] : artist?.artist_chartmetric
      return {
        artistId: e.artist_id,
        artistName: e.artist_name,
        date: e.date,
        venue: e.venue,
        city: e.city,
        country: e.country,
        imageUrl: cm?.image_url ?? null,
      }
    })

    return NextResponse.json({
      milestones,
      trendingYoutube: youtubeRes.data ?? [],
      upcomingEvents,
    })
  } catch (err) {
    console.error('[GET /api/dashboard/overview]', err)
    return NextResponse.json({ error: 'Failed to fetch overview' }, { status: 500 })
  }
}
