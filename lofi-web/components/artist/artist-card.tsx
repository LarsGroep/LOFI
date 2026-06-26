"use client"

import { Star, ArrowUpRight, ArrowDownRight, Calendar, Users } from "lucide-react"

type ArtistStatus = "pending" | "candidate" | "accepted" | "booked" | "rejected"
type Verdict = "Book Now" | "Strong Watch" | "Monitor" | "Pass" | null

interface ArtistCardProps {
  id: string
  name: string
  imageUrl: string | null
  status: ArtistStatus
  spotifyDelta30d: number | null
  raEventCount: number | null
  spMonthlyListeners?: number | null
  lofiFitScore?: number | null
  verdict?: Verdict
  isFavorite: boolean
  onFavoriteToggle: (id: string) => void
  onClick: (id: string) => void
}

const STATUS_STYLES: Record<ArtistStatus, { label: string; className: string }> = {
  pending: { label: "Pending", className: "bg-slate-700 text-slate-300" },
  candidate: { label: "Candidate", className: "bg-indigo-500/20 text-indigo-400" },
  accepted: { label: "Accepted", className: "bg-cyan-500/20 text-cyan-400" },
  booked: { label: "Booked", className: "bg-green-500/20 text-green-400" },
  rejected: { label: "Rejected", className: "bg-red-500/20 text-red-400" },
}

const VERDICT_STYLES: Record<NonNullable<Verdict>, string> = {
  "Book Now": "bg-green-500/20 text-green-400",
  "Strong Watch": "bg-indigo-500/20 text-indigo-400",
  "Monitor": "bg-amber-500/20 text-amber-400",
  "Pass": "bg-slate-700 text-slate-400",
}

function fmt(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—"
  if (n >= 999_500) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}K`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(Math.round(n))
}

function MetricBar({ label, value, max = 100 }: { label: string; value: number | null; max?: number }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(max, value)) / max * 100
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="font-medium text-slate-200">{value == null ? "—" : Math.round(value)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-indigo-400"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export default function ArtistCard({
  id,
  name,
  imageUrl,
  status,
  spotifyDelta30d,
  raEventCount,
  spMonthlyListeners,
  lofiFitScore,
  verdict,
  isFavorite,
  onFavoriteToggle,
  onClick,
}: ArtistCardProps) {
  const statusStyle = STATUS_STYLES[status]
  const verdictStyle = verdict ? VERDICT_STYLES[verdict] : null
  const deltaPositive = spotifyDelta30d !== null && spotifyDelta30d >= 0
  const firstLetter = name.trim().charAt(0).toUpperCase() || "?"

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onClick(id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(id) }
      }}
      className="group flex w-full cursor-pointer flex-col gap-3 rounded-xl border border-white/5 bg-[#161b27] p-3 transition-colors hover:border-indigo-500/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50"
    >
      {/* Image */}
      <div className="relative aspect-square w-full overflow-hidden rounded-lg">
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl} alt={name} crossOrigin="anonymous" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-indigo-600 to-slate-800">
            <span className="text-4xl font-bold text-white/90">{firstLetter}</span>
          </div>
        )}

        {/* Status badge (top-left) */}
        <span className={`absolute left-2 top-2 rounded-full px-2 py-0.5 text-xs font-medium ${statusStyle.className}`}>
          {statusStyle.label}
        </span>

        {/* Favorite star (top-right) */}
        <button
          type="button"
          aria-label={isFavorite ? `Remove ${name} from favorites` : `Add ${name} to favorites`}
          aria-pressed={isFavorite}
          onClick={(e) => { e.stopPropagation(); onFavoriteToggle(id) }}
          className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-black/40 backdrop-blur-sm transition-colors hover:bg-black/60"
        >
          <Star className={isFavorite ? "fill-yellow-400 text-yellow-400" : "text-white/80"} size={16} />
        </button>
      </div>

      {/* Name */}
      <h3 className="text-base font-semibold leading-tight text-slate-100">{name}</h3>

      {/* Metric bars */}
      <div className="flex flex-col gap-2">
        <MetricBar label="LOFI Fit" value={lofiFitScore ?? null} max={100} />
        <MetricBar label="Spotify Δ30d" value={spotifyDelta30d} max={50} />
      </div>

      {/* Bottom row */}
      <div className="mt-1 flex items-center justify-between gap-2 border-t border-white/5 pt-2">
        <div className="flex items-center gap-3 text-sm">
          {/* Listeners */}
          <span className="flex items-center gap-1 text-slate-400">
            <Users size={13} />
            <span className="text-slate-300">{fmt(spMonthlyListeners)}</span>
          </span>
          {/* 30d delta */}
          <span className={`flex items-center gap-0.5 font-medium ${
            spotifyDelta30d === null ? "text-slate-500" : deltaPositive ? "text-green-400" : "text-red-400"
          }`}>
            {spotifyDelta30d !== null && (deltaPositive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />)}
            {spotifyDelta30d === null ? "" : `${deltaPositive ? "+" : ""}${spotifyDelta30d.toFixed(1)}%`}
          </span>
          {/* RA events */}
          <span className="flex items-center gap-1 text-slate-400">
            <Calendar size={13} />
            {raEventCount ?? 0}
          </span>
        </div>

        {/* AI Verdict */}
        {verdictStyle && (
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${verdictStyle}`}>
            {verdict}
          </span>
        )}
      </div>
    </div>
  )
}
