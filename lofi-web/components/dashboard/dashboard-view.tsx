"use client"

import { useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import useSWR from "swr"
import { StatsRow, type DashboardStats } from "@/components/dashboard/stats-row"
import { FiltersBar, type StatusFilter, type SortKey } from "@/components/dashboard/filters-bar"
import { ArtistGrid } from "@/components/dashboard/artist-grid"
import { AddArtistModal } from "@/components/ui/add-artist-modal"
import type { ArtistListItem } from "@/types/supabase"
import { CheckCircle2, PlayCircle, TrendingUp, Plus } from "lucide-react"

const fetcher = (url: string) => fetch(url).then(r => r.json())

interface Milestone {
  id: string
  eventType: string
  eventDate: string | null
  source: string | null
  confirmed: boolean | null
  artistId: string | null
  artistName: string
  imageUrl: string | null
}

interface TrendingSet {
  video_id: string
  title: string | null
  thumbnail_url: string | null
  view_count: number | null
  view_velocity: number | null
  matched_artist_names: string[] | null
  published_at: string | null
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  first_ibiza: "First Ibiza",
  boiler_room: "Boiler Room",
  first_all_night_long: "All-Night-Long",
  first_headline_500: "Headline 500+",
  first_headline_1k: "Headline 1K+",
  first_headline_5k: "Headline 5K+",
  ra_podcast: "RA Podcast",
  festival_main_stage: "Festival Main Stage",
  major_label_signing: "Label Signing",
  agency_signing: "Agency Signing",
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(Math.round(n))
}

function MilestonesStrip({ milestones, onArtistClick }: { milestones: Milestone[]; onArtistClick: (id: string) => void }) {
  if (!milestones.length) return null
  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <CheckCircle2 size={16} className="text-indigo-400" />
        <h2 className="text-sm font-semibold text-[#f1f5f9]">Recent Milestones</h2>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-1">
        {milestones.map(m => (
          <button
            key={m.id}
            type="button"
            onClick={() => m.artistId && onArtistClick(m.artistId)}
            disabled={!m.artistId}
            className="flex shrink-0 items-center gap-3 rounded-xl border border-[#1e2535] bg-[#161b27] px-4 py-3 transition hover:border-[#6366f1]/40 disabled:cursor-default"
          >
            <div className="size-10 shrink-0 overflow-hidden rounded-full bg-[#1e2535]">
              {m.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={m.imageUrl} alt={m.artistName} className="size-full object-cover" crossOrigin="anonymous" />
              ) : (
                <div className="flex size-full items-center justify-center text-sm font-bold text-[#818cf8]">
                  {m.artistName.charAt(0)}
                </div>
              )}
            </div>
            <div className="text-left">
              <p className="text-sm font-medium text-[#f1f5f9]">{m.artistName}</p>
              <p className="text-xs text-[#818cf8]">{EVENT_TYPE_LABELS[m.eventType] ?? m.eventType.replace(/_/g, " ")}</p>
              {m.eventDate && (
                <p className="text-xs text-[#64748b]">{String(m.eventDate).slice(0, 10)}</p>
              )}
            </div>
            {!m.confirmed && (
              <span className="ml-1 rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-400">?</span>
            )}
          </button>
        ))}
      </div>
    </section>
  )
}

function TrendingYoutubeStrip({ sets }: { sets: TrendingSet[] }) {
  if (!sets.length) return null
  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <PlayCircle size={16} className="text-red-400" />
        <h2 className="text-sm font-semibold text-[#f1f5f9]">Trending YouTube Sets</h2>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-1">
        {sets.map(s => (
          <a
            key={s.video_id}
            href={`https://www.youtube.com/watch?v=${s.video_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="group flex w-52 shrink-0 flex-col overflow-hidden rounded-xl border border-[#1e2535] bg-[#161b27] transition hover:border-[#6366f1]/40"
          >
            <div className="relative aspect-video w-full overflow-hidden bg-[#0e1117]">
              {s.thumbnail_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={s.thumbnail_url} alt={s.title ?? ""} className="size-full object-cover transition-transform group-hover:scale-105" />
              ) : (
                <div className="flex size-full items-center justify-center">
                  <PlayCircle size={24} className="text-[#1e2535]" />
                </div>
              )}
              {s.view_velocity && s.view_velocity > 0 && (
                <span className="absolute right-1.5 top-1.5 flex items-center gap-0.5 rounded-full bg-black/60 px-1.5 py-0.5 text-[10px] text-emerald-400">
                  <TrendingUp size={9} /> {fmt(s.view_velocity)}/day
                </span>
              )}
            </div>
            <div className="p-2">
              <p className="line-clamp-2 text-xs font-medium leading-snug text-[#f1f5f9]">{s.title ?? "Untitled"}</p>
              <p className="mt-1 text-[10px] text-[#64748b]">{fmt(s.view_count)} views</p>
            </div>
          </a>
        ))}
      </div>
    </section>
  )
}

interface ServerStats {
  total: number
  booked: number
  trending: number
  withMemo: number
}

interface DashboardViewProps {
  artists: ArtistListItem[]
  onArtistClick: (id: string) => void
  initialSearch?: string
}

export function DashboardView({ artists, onArtistClick, initialSearch = "" }: DashboardViewProps) {
  const router = useRouter()
  const [favorites, setFavorites] = useState<Set<string>>(new Set())
  const [status, setStatus] = useState<StatusFilter>("all")
  const [sort, setSort] = useState<SortKey>("composite")
  const [search, setSearch] = useState(initialSearch)
  const [addModalOpen, setAddModalOpen] = useState(false)

  const { data: overview } = useSWR<{ milestones: Milestone[]; trendingYoutube: TrendingSet[] }>(
    "/api/dashboard/overview",
    fetcher,
    { revalidateOnFocus: false }
  )

  const { data: serverStats } = useSWR<ServerStats>("/api/stats", fetcher, { revalidateOnFocus: false })

  const stats: DashboardStats = useMemo(() => ({
    total: serverStats?.total ?? artists.length,
    bookedThisMonth: serverStats?.booked ?? artists.filter(a => a.status === "booked").length,
    trending: serverStats?.trending ?? artists.filter(a => (a.xgboostGrowth90d ?? 0) > 10).length,
    needsAttention: serverStats ? (serverStats.total - serverStats.withMemo) : artists.filter(a => a.verdict === null).length,
  }), [serverStats, artists])

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase()
    const filtered = artists.filter(a => {
      const matchesStatus = status === "all" || a.status === status
      const matchesSearch = query === "" || a.name.toLowerCase().includes(query)
      return matchesStatus && matchesSearch
    })
    const verdictOrder: Record<string, number> = { "Book Now": 4, "Strong Watch": 3, "Monitor": 2, "Pass": 1 }
    const sorted = [...filtered]
    switch (sort) {
      case "composite":
        sorted.sort((a, b) =>
          (verdictOrder[b.verdict ?? ""] ?? 0) - (verdictOrder[a.verdict ?? ""] ?? 0) ||
          (b.lofiFitScore ?? -1) - (a.lofiFitScore ?? -1))
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
    setFavorites(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const cardArtists = useMemo(() =>
    visible.map(a => ({
      id: a.id,
      name: a.name,
      imageUrl: a.imageUrl,
      status: a.status,
      scores: { momentum: null, growth: null, marketRelevance: null, futurePotential: null, confidence: null },
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
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#f1f5f9]">Dashboard</h1>
          <p className="text-sm text-[#94a3b8]">Artist Intelligence — LOFI Amsterdam</p>
        </div>
        <button
          type="button"
          onClick={() => setAddModalOpen(true)}
          className="flex shrink-0 items-center gap-2 rounded-lg bg-indigo-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-indigo-400"
        >
          <Plus size={15} /> Add Artist
        </button>
      </header>

      {addModalOpen && (
        <AddArtistModal
          onClose={() => setAddModalOpen(false)}
          onNavigate={id => router.push(`/artist/${id}`)}
        />
      )}

      <StatsRow stats={stats} />

      {/* Milestones strip */}
      {overview?.milestones?.length ? (
        <MilestonesStrip milestones={overview.milestones} onArtistClick={id => router.push(`/artist/${id}`)} />
      ) : null}

      {/* Trending YouTube sets */}
      {overview?.trendingYoutube?.length ? (
        <TrendingYoutubeStrip sets={overview.trendingYoutube} />
      ) : null}

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
