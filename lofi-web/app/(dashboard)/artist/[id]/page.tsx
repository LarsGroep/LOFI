'use client'

import { use, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import ArtistProfile from '@/components/artist/artist-profile'
import AIBookingMemo from '@/components/artist/ai-booking-memo'
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

  // Map DB notes (artist_feedback + artist_notes) to profile prop shape
  const notes = [
    ...(artist.feedback ?? []).map(f => ({
      id: f.id,
      text: f.notes ?? f.field_value ?? '',
      createdAt: f.created_at ?? '',
    })),
  ].filter(n => n.text)

  // Map RA events to milestone format
  const events = (artist.raEvents ?? [])
    .filter(e => e.date)
    .map(e => ({
      date: e.date!,
      venue: e.venue ?? 'Unknown venue',
      attending: e.venue_capacity ?? 0,
      festival: false,
    }))

  // Extract Spotify listener timeseries for the chart
  const growthData = (artist.timeseries ?? []).map(p => ({
    date: (p.date as string).slice(0, 7), // YYYY-MM
    listeners: (p as { listeners?: number }).listeners ?? 0,
  }))

  // Map aiMemo to component shape
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

  return (
    <div className="flex flex-col gap-6">
      {/* AI Booking Memo — top of page, replaces technical scores */}
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
        }}
        scores={{
          momentum: 0,
          growth: 0,
          marketRelevance: 0,
          futurePotential: 0,
          confidence: 0,
        }}
        bookingSignals={{
          xgboost: Math.round((artist.xgboostGrowth90d ?? 0) * 100),
          scene: artist.raEventCount ? Math.min(100, artist.raEventCount * 5) : 0,
          lofiFit: Math.round(artist.lofiFeel?.score ?? 0),
          composite: Math.round(
            ((artist.xgboostGrowth90d ?? 0) * 100 * 0.4) +
            (Math.min(100, (artist.raEventCount ?? 0) * 5) * 0.35) +
            ((artist.lofiFeel?.score ?? 0) * 0.25)
          ),
        }}
        growthData={growthData}
        events={events}
        notes={notes}
        onAddNote={handleAddNote}
        isFavorite={isFavorite}
        onFavoriteToggle={() => setIsFavorite(v => !v)}
        onBack={() => router.push('/dashboard')}
      />
    </div>
  )
}
