'use client'

import { use, useState, useCallback, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import ArtistProfile from '@/components/artist/artist-profile'
import AIBookingMemo from '@/components/artist/ai-booking-memo'
import ArtistChat from '@/components/artist/artist-chat'
import type { ArtistDetail, ArtistAiMemoRow } from '@/types/supabase'

const fetcher = (url: string) => fetch(url).then(r => { if (!r.ok) throw new Error('fetch failed'); return r.json() })

export default function ArtistProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const router = useRouter()

  const { data: artist, isLoading, error, mutate } = useSWR<ArtistDetail>(
    `/api/artists/${id}`,
    fetcher,
    { revalidateOnFocus: false }
  )

  const [isFavorite, setIsFavorite] = useState(false)
  const [memoLoading, setMemoLoading] = useState(false)
  const autoMemoFiredRef = useRef(false)

  const handleAddNote = useCallback(async (text: string) => {
    await fetch(`/api/artists/${id}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    mutate()
  }, [id, mutate])

  const handleRegenMemo = useCallback(async () => {
    setMemoLoading(true)
    try {
      await fetch(`/api/artists/${id}/memo`, { method: 'POST' })
      mutate()
    } finally {
      setMemoLoading(false)
    }
  }, [id, mutate])

  // Auto-generate memo if artist has loaded and has no memo yet
  useEffect(() => {
    if (artist && artist.aiMemo === null && !autoMemoFiredRef.current) {
      autoMemoFiredRef.current = true
      handleRegenMemo()
    }
  }, [artist, handleRegenMemo])

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="h-48 animate-pulse rounded-xl bg-[#161b27]" />
        <div className="h-32 animate-pulse rounded-xl bg-[#161b27]" />
        <div className="h-64 animate-pulse rounded-xl bg-[#161b27]" />
      </div>
    )
  }

  if (error || !artist) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-red-400">Failed to load artist profile.</p>
      </div>
    )
  }

  const notes = [
    ...(artist.artistNotes ?? []).map(n => ({
      id: n.id,
      text: n.text,
      createdAt: n.created_at,
    })),
    ...(artist.feedback ?? []).map(f => ({
      id: f.id,
      text: f.notes ?? f.field_value ?? '',
      createdAt: f.created_at ?? '',
    })),
  ].filter(n => n.text)

  const events = (artist.raEvents ?? [])
    .filter(e => e.date)
    .map(e => ({
      date: e.date!,
      venue: e.venue ?? 'Unknown venue',
      attending: e.venue_capacity ?? 0,
      festival: false,
      city: e.city ?? undefined,
      country: e.country ?? undefined,
    }))

  const growthData = (artist.timeseries ?? []).map(p => ({
    date: (p.date as string).slice(0, 7),
    listeners: (p as { listeners?: number }).listeners ?? 0,
  }))

  const memo = artist.aiMemo
    ? {
        verdict: artist.aiMemo.verdict as ArtistAiMemoRow['verdict'],
        verdictReason: artist.aiMemo.verdict_reason,
        summary: artist.aiMemo.summary,
        signals: (artist.aiMemo.signals as { label: string; rating: string; detail: string }[]) ?? [],
        opportunities: artist.aiMemo.opportunities ?? [],
        risks: artist.aiMemo.risks ?? [],
        comparablePast: artist.aiMemo.comparable_past ?? [],
        generatedAt: artist.aiMemo.generated_at,
        dataFreshness: artist.aiMemo.data_freshness as 'Fresh' | 'Stale' | 'Partial',
      }
    : null

  const artistContext = [
    artist.genres?.slice(0, 2).join(' / ') ?? '',
    artist.spMonthlyListeners
      ? `${(artist.spMonthlyListeners / 1000).toFixed(0)}K listeners`
      : null,
    artist.xgboostGrowth90d != null
      ? `${artist.xgboostGrowth90d.toFixed(1)}% CPP growth`
      : null,
    artist.lofiFeel?.score != null
      ? `LOFI fit ${Math.round(artist.lofiFeel.score)}/100`
      : null,
  ].filter(Boolean).join(' · ')

  return (
    <div className="flex flex-col gap-6">
      <AIBookingMemo
        memo={memo}
        isLoading={memoLoading}
        onRegenerate={handleRegenMemo}
      />

      <ArtistProfile
        artist={{
          id: artist.id,
          name: artist.name,
          imageUrl: artist.imageUrl,
          status: artist.status,
          genres: artist.genres ?? [],
          description: artist.description,
          recordLabel: artist.recordLabel,
          bookingAgent: artist.bookingAgent,
          currentCity: artist.currentCity,
          hometownCity: artist.hometownCity,
        }}
        bookingSignals={{
          xgboost: artist.growthScore ?? 0,
          scene: artist.sceneScore ?? 0,
          lofiFit: Math.round(artist.lofiFeel?.score ?? 0),
          composite: artist.compositeScore ?? 0,
        }}
        growthData={growthData}
        multiTimeseries={artist.multiTimeseries ?? []}
        events={events}
        notes={notes}
        onAddNote={handleAddNote}
        isFavorite={isFavorite}
        onFavoriteToggle={() => setIsFavorite(v => !v)}
        onBack={() => router.push('/dashboard')}
        tracks={artist.tracks ?? []}
        validationEvents={artist.validationEvents ?? []}
        similarArtists={artist.similarArtists ?? []}
        socialLinks={artist.socialLinks ?? []}
        fanCities={artist.fanCities ?? []}
        noteworthy={artist.noteworthy ?? []}
        pfFans={artist.pfFans}
        pfTotalPerformances={artist.pfTotalPerformances}
        pfUpcomingPerformances={artist.pfUpcomingPerformances}
        pfGenres={artist.pfGenres}
        instagramAudience={artist.instagramAudience}
        xgboostGrowth90d={artist.xgboostGrowth90d}
        albums={artist.albums ?? []}
        cmArtistScore={artist.cmArtistScore}
        cmArtistRank={artist.cmArtistRank}
        spMonthlyListeners={artist.spMonthlyListeners}
        igFollowers={artist.igFollowers}
        tiktokFollowers={artist.tiktokFollowers}
        lfmListeners={artist.lfmListeners}
        fiveScores={artist.fiveScores}
        mlFeatures={artist.mlFeatures}
        playlists={artist.playlists ?? []}
        beatportChartEntries={artist.beatportChartEntries ?? []}
        traxsourceChartEntries={artist.traxsourceChartEntries ?? []}
        pfEvents={artist.pfEvents ?? []}
        tiktokAudience={artist.tiktokAudience}
      />

      <ArtistChat
        artistId={id}
        artistName={artist.name}
        artistContext={artistContext}
      />
    </div>
  )
}
