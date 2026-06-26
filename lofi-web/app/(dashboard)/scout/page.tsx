"use client"

import { useState } from "react"
import {
  Zap,
  TrendingUp,
  Star,
  RefreshCw,
  ArrowUpRight,
  ChevronRight,
} from "lucide-react"
import { ArtistRadarCard, type ArtistSignal } from "@/components/scout/artist-radar-card"

interface ScoutData {
  breaking: ArtistSignal[]
  rising: ArtistSignal[]
  watchlistAlerts: ArtistSignal[]
}

const GENRES = ["All", "Tech-House", "House", "Techno", "Afro House"] as const
const REGIONS = ["All", "Netherlands", "Europe", "Global"] as const
const WINDOWS = ["7d", "14d", "30d"] as const

// ---- Mock data (TODO: replace with SWR fetch from Supabase) ----
function spark(seed: number): number[] {
  return Array.from({ length: 30 }, (_, i) => 40 + Math.sin(i / 4 + seed) * 12 + i * (seed % 3))
}

const MOCK: ScoutData = {
  breaking: [
    { id: "verraco", name: "Verraco", imageUrl: null, genre: "Tech-House", momentumScore: 84, momentumDelta: 22, trigger: "RA event surge — 4 festival adds in 14d", sparklineData: spark(1) },
    { id: "sansibar", name: "Sansibar", imageUrl: null, genre: "Afro House", momentumScore: 78, momentumDelta: 18, trigger: "Spotify +40K monthly listeners", sparklineData: spark(2) },
    { id: "kettama", name: "KETTAMA", imageUrl: null, genre: "House", momentumScore: 71, momentumDelta: 15, trigger: "New festival booking — Awakenings 2025", sparklineData: spark(3) },
  ],
  rising: [
    { id: "lostsoul", name: "Lost Souls of Saturn", imageUrl: null, genre: "Techno", momentumScore: 66, momentumDelta: 9, trigger: "Steady playlist growth 3 months", sparklineData: spark(4) },
    { id: "azu", name: "Azu Tiwaline", imageUrl: null, genre: "Techno", momentumScore: 61, momentumDelta: 7, trigger: "Consistent NL booking density", sparklineData: spark(5) },
    { id: "dexphase", name: "DexPhase", imageUrl: null, genre: "Tech-House", momentumScore: 58, momentumDelta: 6, trigger: "Upward Beatport chart trend", sparklineData: spark(6) },
  ],
  watchlistAlerts: [
    { id: "enrico", name: "Enrico Sangiuliano", imageUrl: null, genre: "Techno", momentumScore: 88, momentumDelta: 12, trigger: "Agency upgraded booking tier", sparklineData: spark(7) },
  ],
}

function StatTile({
  label,
  value,
  delta,
  icon: Icon,
}: {
  label: string
  value: string
  delta?: string
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

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "bg-[#6366f1] text-white"
          : "bg-[#1e2535] text-[#94a3b8] hover:bg-[#252d3f] hover:text-[#f1f5f9]"
      }`}
    >
      {children}
    </button>
  )
}

function SwimLane({
  title,
  icon: Icon,
  iconClass,
  signals,
}: {
  title: string
  icon: React.ComponentType<{ size?: number; className?: string }>
  iconClass: string
  signals: ArtistSignal[]
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
        <a
          href="#"
          className="inline-flex items-center gap-0.5 text-sm font-medium text-[#6366f1] hover:text-[#818cf8]"
        >
          View All
          <ChevronRight size={14} aria-hidden="true" />
        </a>
      </div>
      {signals.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 bg-[#161b27]/50 p-8 text-center text-sm text-[#64748b]">
          No artists matching this signal right now
        </div>
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {signals.map((s) => (
            <ArtistRadarCard key={s.id} signal={s} />
          ))}
        </div>
      )}
    </section>
  )
}

export default function ScoutPage() {
  const [genre, setGenre] = useState<(typeof GENRES)[number]>("All")
  const [region, setRegion] = useState<(typeof REGIONS)[number]>("All")
  const [window, setWindow] = useState<(typeof WINDOWS)[number]>("14d")
  const [refreshing, setRefreshing] = useState(false)

  const data = MOCK

  function handleRefresh() {
    setRefreshing(true)
    // TODO: trigger real intelligence refresh
    setTimeout(() => setRefreshing(false), 1500)
  }

  return (
    <div className="flex flex-col gap-6">
      {/* HEADER */}
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold text-[#f1f5f9]">Scout</h1>
          <p className="text-sm text-[#94a3b8]">Emerging artists — 6 to 18 months ahead of the market</p>
          <p className="text-xs text-[#64748b]">Last updated 12 minutes ago</p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-[#6366f1] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#818cf8] disabled:opacity-60"
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} aria-hidden="true" />
          {refreshing ? "Refreshing…" : "Refresh Intelligence"}
        </button>
      </header>

      {/* RADAR SUMMARY ROW */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatTile label="Breaking This Week" value={String(data.breaking.length)} delta="vs last week" icon={Zap} />
        <StatTile label="New Artist Additions" value="12" icon={TrendingUp} />
        <StatTile label="Watchlist Changes" value={String(data.watchlistAlerts.length)} delta="+1 today" icon={Star} />
      </div>

      {/* FILTER BAR */}
      <div className="flex flex-col gap-3 rounded-xl border border-white/5 bg-[#161b27] p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-xs font-medium uppercase tracking-wide text-[#64748b]">Genre</span>
          {GENRES.map((g) => (
            <Chip key={g} active={genre === g} onClick={() => setGenre(g)}>
              {g}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-xs font-medium uppercase tracking-wide text-[#64748b]">Region</span>
          {REGIONS.map((r) => (
            <Chip key={r} active={region === r} onClick={() => setRegion(r)}>
              {r}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-xs font-medium uppercase tracking-wide text-[#64748b]">Window</span>
          {WINDOWS.map((w) => (
            <Chip key={w} active={window === w} onClick={() => setWindow(w)}>
              {w}
            </Chip>
          ))}
        </div>
      </div>

      {/* SWIM LANES */}
      <SwimLane title="Breaking" icon={Zap} iconClass="text-green-400" signals={data.breaking} />
      <SwimLane title="On The Rise" icon={TrendingUp} iconClass="text-[#6366f1]" signals={data.rising} />
      <SwimLane title="Watch List Alerts" icon={Star} iconClass="text-amber-400" signals={data.watchlistAlerts} />
    </div>
  )
}
