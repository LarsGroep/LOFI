"use client"

import { useMemo, useState } from "react"
import { StatsRow, type DashboardStats } from "@/components/dashboard/stats-row"
import { FiltersBar, type StatusFilter, type SortKey } from "@/components/dashboard/filters-bar"
import { ArtistGrid } from "@/components/dashboard/artist-grid"
import type { ArtistListItem } from "@/types/supabase"

function computeStats(artists: ArtistListItem[]): DashboardStats {
  return {
    total: artists.length,
    bookedThisMonth: artists.filter((a) => a.status === "booked").length,
    trending: artists.filter((a) => (a.xgboostGrowth90d ?? 0) > 0.15).length,
    needsAttention: artists.filter((a) => a.verdict === null).length,
  }
}

interface DashboardViewProps {
  artists: ArtistListItem[]
  onArtistClick: (id: string) => void
}

export function DashboardView({ artists, onArtistClick }: DashboardViewProps) {
  const [favorites, setFavorites] = useState<Set<string>>(new Set())
  const [status, setStatus] = useState<StatusFilter>("all")
  const [sort, setSort] = useState<SortKey>("composite")
  const [search, setSearch] = useState("")

  const stats = useMemo(() => computeStats(artists), [artists])

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase()
    const filtered = artists.filter((a) => {
      const matchesStatus = status === "all" || a.status === status
      const matchesSearch = query === "" || a.name.toLowerCase().includes(query)
      return matchesStatus && matchesSearch
    })

    const verdictOrder: Record<string, number> = {
      "Book Now": 4, "Strong Watch": 3, "Monitor": 2, "Pass": 1,
    }

    const sorted = [...filtered]
    switch (sort) {
      case "composite":
        sorted.sort((a, b) =>
          (verdictOrder[b.verdict ?? ""] ?? 0) - (verdictOrder[a.verdict ?? ""] ?? 0) ||
          (b.lofiFitScore ?? -1) - (a.lofiFitScore ?? -1)
        )
        break
      case "momentum":
        sorted.sort((a, b) => (b.xgboostGrowth90d ?? -99) - (a.xgboostGrowth90d ?? -99))
        break
      case "growth":
        sorted.sort((a, b) => (b.spotifyDelta30d ?? -99) - (a.spotifyDelta30d ?? -99))
        break
      case "name":
        sorted.sort((a, b) => a.name.localeCompare(b.name))
        break
      case "recent":
        sorted.sort((a, b) => (b.spotifyDelta30d ?? -99) - (a.spotifyDelta30d ?? -99))
        break
    }
    return sorted
  }, [artists, status, sort, search])

  const handleFavoriteToggle = (id: string) => {
    setFavorites((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Map ArtistListItem to ArtistCard props
  const cardArtists = useMemo(() =>
    visible.map((a) => ({
      id: a.id,
      name: a.name,
      imageUrl: a.imageUrl,
      status: a.status,
      scores: {
        momentum: null,
        growth: null,
        marketRelevance: null,
        futurePotential: null,
        confidence: null,
      },
      composite: null,
      spotifyDelta30d: a.spotifyDelta30d ?? null,
      raEventCount: a.raEventCount ?? null,
      isFavorite: favorites.has(a.id),
      verdict: a.verdict,
      lofiFitScore: a.lofiFitScore,
      spMonthlyListeners: a.spMonthlyListeners,
    })),
    [visible, favorites]
  )

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-[#f1f5f9]">Dashboard</h1>
        <p className="text-sm text-[#94a3b8]">Artist Intelligence — LOFI Amsterdam</p>
      </header>

      <StatsRow stats={stats} />

      <FiltersBar
        status={status}
        onStatusChange={setStatus}
        sort={sort}
        onSortChange={setSort}
        search={search}
        onSearchChange={setSearch}
      />

      <ArtistGrid
        artists={cardArtists}
        onFavoriteToggle={handleFavoriteToggle}
        onArtistClick={onArtistClick}
      />
    </div>
  )
}
