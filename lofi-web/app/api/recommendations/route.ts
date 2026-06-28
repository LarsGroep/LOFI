import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const artistId = searchParams.get('artist_id')
  const limit = Math.min(Number(searchParams.get('limit') ?? 15), 30)

  if (!artistId) return NextResponse.json({ error: 'artist_id required' }, { status: 400 })

  try {
    const supabase = createServiceClient()

    // 1. Get artist name + booked roster names (for scoring signal)
    const [artistRes, bookedRes] = await Promise.all([
      supabase.from('artists').select('id, name').eq('id', artistId).single(),
      supabase.from('artists').select('name').eq('candidate_status', 'booked'),
    ])

    if (artistRes.error || !artistRes.data) {
      return NextResponse.json({ error: 'Artist not found' }, { status: 404 })
    }

    const artistName = artistRes.data.name
    const bookedNames = new Set((bookedRes.data ?? []).map((a: any) => (a.name as string).toLowerCase()))

    // 2. Get all this artist's RA events with lineups
    const { data: events } = await supabase
      .from('ra_events')
      .select('lineup, venue, city, country, date')
      .eq('artist_id', artistId)
      .not('lineup', 'is', null)
      .limit(200)

    if (!events?.length) {
      return NextResponse.json({ recommendations: [], totalEvents: 0 })
    }

    // 3. Count co-occurrences across lineups
    const coMap = new Map<string, { count: number; venues: Set<string>; cities: Set<string>; latestDate: string }>()
    for (const event of events) {
      const lineup = event.lineup as string[]
      for (const name of lineup) {
        if (name.toLowerCase() === artistName.toLowerCase()) continue
        if (!coMap.has(name)) {
          coMap.set(name, { count: 0, venues: new Set(), cities: new Set(), latestDate: event.date ?? '' })
        }
        const entry = coMap.get(name)!
        entry.count++
        if (event.venue) entry.venues.add(event.venue)
        if (event.city) entry.cities.add(event.city)
        if (event.date && event.date > entry.latestDate) entry.latestDate = event.date
      }
    }

    // 4. Top co-artists sorted by co-occurrence count
    const topNames = [...coMap.entries()]
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, limit * 3) // fetch extra to account for unmatched
      .map(([name]) => name)

    if (!topNames.length) return NextResponse.json({ recommendations: [], totalEvents: events.length })

    // 5. Match against artists table (by name, case-insensitive)
    const { data: matched } = await supabase
      .from('artists')
      .select(`
        id, name, candidate_status,
        artist_chartmetric (image_url, genres, sp_monthly_listeners, booking_agent),
        xgboost_predictions (predicted_growth_90d),
        artist_ai_memo (verdict)
      `)
      .in('name', topNames)
      .limit(limit * 2)

    const matchedMap = new Map<string, any>((matched ?? []).map((a: any) => [a.name.toLowerCase(), a]))

    // 6. Build recommendations (matched only, sorted by co-count)
    const recs = topNames
      .map(name => {
        const co = coMap.get(name)!
        const artist = matchedMap.get(name.toLowerCase())
        if (!artist) return null
        const cm = Array.isArray(artist.artist_chartmetric) ? artist.artist_chartmetric[0] : artist.artist_chartmetric
        const xg = Array.isArray(artist.xgboost_predictions) ? artist.xgboost_predictions[0] : artist.xgboost_predictions
        const memo = Array.isArray(artist.artist_ai_memo) ? artist.artist_ai_memo[0] : artist.artist_ai_memo
        return {
          artistId: artist.id,
          name: artist.name,
          status: artist.candidate_status,
          imageUrl: cm?.image_url ?? null,
          genres: cm?.genres ?? null,
          spMonthlyListeners: cm?.sp_monthly_listeners ?? null,
          bookingAgent: cm?.booking_agent ?? null,
          xgboostGrowth90d: xg?.predicted_growth_90d ?? null,
          verdict: memo?.verdict ?? null,
          coCount: co.count,
          sharedVenues: [...co.venues].slice(0, 3),
          sharedCities: [...co.cities].slice(0, 3),
          latestSharedEvent: co.latestDate,
          isOnLofiRoster: bookedNames.has(artist.name.toLowerCase()),
        }
      })
      .filter(Boolean)
      .slice(0, limit)

    return NextResponse.json({ recommendations: recs, totalEvents: events.length, artistName })
  } catch (err) {
    console.error('[GET /api/recommendations]', err)
    return NextResponse.json({ error: 'Failed to compute recommendations' }, { status: 500 })
  }
}
