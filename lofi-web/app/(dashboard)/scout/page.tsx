"use client"

import { useMemo, useState } from "react"
import useSWR from "swr"
import { Zap, TrendingUp, Star, RefreshCw, ArrowUpRight, ChevronRight } from "lucide-react"
import { ArtistRadarCard, type ArtistSignal } from "@/components/scout/artist-radar-card"
import type { ArtistListItem } from "@/types/supabase"

const fetcher = (url: string) => fetch(url).then(r => r.json())

const GENRES = ["All", "Tech-House", "House", "Techno", "Afro House", "Melodic Techno"] as const
type Genre = (typeof GENRES)[number]

function pseudoSparkline(growth: number, seed: number): number[] {
  return Array.from({ length: 20 }, (_, i) => {
    const base = 45
    const trend = growth * 120 * (i / 19)
    const noise = Math.sin(i * 1.8 + seed) * 4
    return Math.max(5, base + trend + noise)
  })
}

function toSignal(a: ArtistListItem, seed: number): ArtistSignal {
  const growth = a.xgboostGrowth90d ?? 0
  const lofi = a.lofiFitScore ?? 0
  const momentumScore = Math.round(Math.max(lofi * 0.5 + growth * 100 * 0.5, lofi * 0.7))
  const momentumDelta = Math.round(growth * 100)

  const trigger = a.verdictReason
    ? a.verdictReason.slice(0, 70) + (a.verdictReason.length > 70 ? "…" : "")
    : a.verdict
    ? `AI verdict: ${a.verdict}`
    : a.xgboostGrowth90d != null
    ? `XGBoost: +${(a.xgboostGrowth90d * 100).toFixed(1)}% predicted 90d growth`
    : `LOFI fit score: ${Math.round(lofi)}`

  return {
    id: a.id,
    name: a.name,
    imageUrl: a.imageUrl,
    genre: a.genres?.[0] ?? "Electronic",
    momentumScore: Math.min(99, Math.max(0, momentumScore)),
    momentumDelta,
    trigger,
    sparklineData: pseudoSparkline(growth, seed),
  }
}

function matchesGenre(a: ArtistListItem, genre: Genre): boolean {
  if (genre === "All") return true
  return (a.genres ?? []).some(g => g.toLowerCase().includes(genre.toLowerCase()))
}

function StatTile({ label, value, delta, icon: Icon }: {
  label: string; value: string; delta?: string
  icon: React.ComponentType<{ size?: number; className?: string }>
}) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-white/5 bg-[#161b27] p-4">
      <div className="flex flex-col gap-1">
        <span className="text-sm text-[#94a3b8]">{label}</span>
        <span className="text-2xl font-bold text-[#f1f5f9]">{value}</span>
        {delta && (
          <span className="inline-flex items-center gap-0.5 text-xs font-medium text-green-400">
            <ArrowUpRight size={12} aria-hidden="true" />
            {delta}
          </span>
        )}
      </div>
      <div className="flex size-10 items-center justify-center rounded-lg bg-[#6366f1]/15">
        <Icon size={20} className="text-[#6366f1]" />
      </div>
    </div>
  )
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
        active ? "bg-[#6366f1] text-white" : "bg-[#1e2535] text-[#94a3b8] hover:bg-[#252d3f] hover:text-[#f1f5f9]"
      }`}
    >
      {children}
    </button>
  )
}

function SwimLane({ title, icon: Icon, iconClass, signals, href }: {
  title: string
  icon: React.ComponentType<{ size?: number; className?: string }>
  iconClass: string
  signals: ArtistSignal[]
  href?: string
}) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon size={18} className={iconClass} />
          <h2 className="text-lg font-semibold text-[#f1f5f9]">{title}</h2>
          <span className="rounded-full bg-[#1e2535] px-2 py-0.5 text-xs font-medium text-[#94a3b8]">
            {signals.length}
          </span>
        </div>
        {href && (
          <a href={href} className="inline-flex items-center gap-0.5 text-sm font-medium text-[#6366f1] hover:text-[#818cf8]">
            View All <ChevronRight size={14} />
          </a>
        )}
      </div>
      {signals.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 bg-[#161b27]/50 p-8 text-center text-sm text-[#64748b]">
          No artists matching this signal right now
        </div>
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {signals.map((s) => <ArtistRadarCard key={s.id} signal={s} />)}
        </div>
      )}
    </section>
  )
}

export default function ScoutPage() {
  const { data, isLoading, mutate } = useSWR<ArtistListItem[]>('/api/artists?limit=500', fetcher, {
    revalidateOnFocus: false,
  })

  const [genre, setGenre] = useState<Genre>("All")
  const [refreshing, setRefreshing] = useState(false)

  async function handleRefresh() {
    setRefreshing(true)
    await mutate()
    setRefreshing(false)
  }

  const { breaking, rising, watchlistAlerts } = useMemo(() => {
    const artists = (data ?? []).filter(a => matchesGenre(a, genre))

    // Breaking: high XGBoost growth (top 5)
    const byGrowth = [...artists]
      .filter(a => a.xgboostGrowth90d != null && a.xgboostGrowth90d > 0.02)
      .sort((a, b) => (b.xgboostGrowth90d ?? 0) - (a.xgboostGrowth90d ?? 0))
      .slice(0, 5)
      .map((a, i) => toSignal(a, i))

    // Rising: strong LOFI fit, moderate growth
    const breakingIds = new Set(byGrowth.map(s => s.id))
    const byLofi = [...artists]
      .filter(a => !breakingIds.has(a.id) && (a.lofiFitScore ?? 0) > 30)
      .sort((a, b) => (b.lofiFitScore ?? 0) - (a.lofiFitScore ?? 0))
      .slice(0, 6)
      .map((a, i) => toSignal(a, i + 10))

    // Watchlist alerts: current candidates with AI memo or strong fit
    const risingIds = new Set(byLofi.map(s => s.id))
    const candidates = [...artists]
      .filter(a => !breakingIds.has(a.id) && !risingIds.has(a.id) && a.status === "candidate" && (a.verdict != null || (a.lofiFitScore ?? 0) > 35))
      .slice(0, 4)
      .map((a, i) => toSignal(a, i + 20))

    return { breaking: byGrowth, rising: byLofi, watchlistAlerts: candidates }
  }, [data, genre])

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold text-[#f1f5f9]">Scout</h1>
          <p className="text-sm text-[#94a3b8]">Emerging artists — 6 to 18 months ahead of the market</p>
          {data && <p className="text-xs text-[#64748b]">Derived from {data.length} tracked artists</p>}
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing || isLoading}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-[#6366f1] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#818cf8] disabled:opacity-60"
        >
          <RefreshCw size={16} className={refreshing || isLoading ? "animate-spin" : ""} />
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      {isLoading ? (
        <div className="grid grid-cols-3 gap-4">
          {[0, 1, 2].map(i => <div key={i} className="h-20 animate-pulse rounded-xl bg-[#161b27]" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatTile label="Breaking (high growth)" value={String(breaking.length)} icon={Zap} />
          <StatTile label="Rising (strong LOFI fit)" value={String(rising.length)} icon={TrendingUp} />
          <StatTile label="Candidate alerts" value={String(watchlistAlerts.length)} icon={Star} />
        </div>
      )}

      <div className="flex flex-col gap-3 rounded-xl border border-white/5 bg-[#161b27] p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-xs font-medium uppercase tracking-wide text-[#64748b]">Genre</span>
          {GENRES.map((g) => (
            <Chip key={g} active={genre === g} onClick={() => setGenre(g)}>{g}</Chip>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-[#161b27]" />
      ) : (
        <>
          <SwimLane title="Breaking" icon={Zap} iconClass="text-green-400" signals={breaking} href="/dashboard?sort=growth" />
          <SwimLane title="On The Rise" icon={TrendingUp} iconClass="text-[#6366f1]" signals={rising} href="/dashboard?sort=lofi" />
          <SwimLane title="Candidate Alerts" icon={Star} iconClass="text-amber-400" signals={watchlistAlerts} href="/pipeline" />
        </>
      )}
    </div>
  )
}
