"use client"

import { useState } from "react"
import {
  ArrowLeft,
  Star,
  TrendingUp,
  Calendar,
  Sparkles,
  Music2,
  Users,
  CheckCircle2,
  Circle,
} from "lucide-react"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import type { TrackRow, ValidationEventRow, MultiTimeseriesItem } from "@/types/supabase"

function fmt(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—"
  if (n >= 999_500) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}K`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(Math.round(n))
}

export interface ArtistProfileProps {
  artist: { id: string; name: string; imageUrl: string | null; status: string; genres: string[] }
  bookingSignals: { xgboost: number; scene: number; lofiFit: number; composite: number }
  growthData: Array<{ date: string; listeners: number }>
  multiTimeseries: MultiTimeseriesItem[]
  events: Array<{ date: string; venue: string; attending: number; festival: boolean }>
  notes: Array<{ id: string; text: string; createdAt: string }>
  onAddNote: (text: string) => void
  isFavorite: boolean
  onFavoriteToggle: () => void
  onBack?: () => void
  tracks: TrackRow[]
  validationEvents: ValidationEventRow[]
  similarArtists: string[]
}

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-slate-700 text-slate-300",
  candidate: "bg-indigo-500/20 text-indigo-400",
  accepted: "bg-cyan-500/20 text-cyan-400",
  booked: "bg-green-500/20 text-green-400",
  rejected: "bg-red-500/20 text-red-400",
}

function getVerdict(composite: number): { label: string; className: string; ring: string } {
  if (composite >= 65) return { label: "Book", className: "bg-green-500/20 text-green-400", ring: "#22c55e" }
  if (composite >= 45) return { label: "Promising", className: "bg-indigo-500/20 text-indigo-400", ring: "#6366f1" }
  if (composite >= 30) return { label: "Uncertain", className: "bg-amber-500/20 text-amber-400", ring: "#f59e0b" }
  return { label: "Not recommended", className: "bg-slate-700 text-slate-300", ring: "#64748b" }
}

function ScoreRing({
  value,
  size = 64,
  stroke = 6,
  color = "#6366f1",
  children,
}: {
  value: number
  size?: number
  stroke?: number
  color?: string
  children?: React.ReactNode
}) {
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (Math.max(0, Math.min(100, value)) / 100) * circumference
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          fill="none"
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center">{children}</span>
    </div>
  )
}

function SignalBar({ label, weight, value }: { label: string; weight: number; value: number }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-[#1e2535] p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-200">{label}</span>
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-400">{weight}% weight</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-indigo-400"
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
      <span className="text-2xl font-bold text-slate-100">{Math.round(value)}</span>
    </div>
  )
}

const PLATFORM_COLORS: Record<string, string> = {
  spotify: "#1DB954",
  instagram: "#E1306C",
  tiktok: "#69C9D0",
  soundcloud: "#FF5500",
}

export default function ArtistProfile({
  artist,
  bookingSignals,
  growthData,
  multiTimeseries,
  events,
  notes,
  onAddNote,
  isFavorite,
  onFavoriteToggle,
  onBack,
  tracks,
  validationEvents,
  similarArtists,
}: ArtistProfileProps) {
  const [draft, setDraft] = useState("")
  const [activePlatform, setActivePlatform] = useState<string>(
    multiTimeseries[0]?.platform ?? "spotify"
  )
  const verdict = getVerdict(bookingSignals.composite)
  const firstLetter = artist.name.trim().charAt(0).toUpperCase() || "?"
  const statusClass = STATUS_STYLES[artist.status] ?? STATUS_STYLES.pending

  const sortedEvents = [...events].sort((a, b) => +new Date(a.date) - +new Date(b.date))

  const activeTs = multiTimeseries.find(m => m.platform === activePlatform)
  const chartData = activeTs
    ? activeTs.data.map(p => ({ date: p.date.slice(0, 7), value: p.value }))
    : growthData.map(p => ({ date: p.date.slice(0, 7), value: p.listeners }))

  function handleAdd() {
    const text = draft.trim()
    if (!text) return
    onAddNote(text)
    setDraft("")
  }

  return (
    <div className="flex flex-col gap-6">
      {/* 1. HERO STRIP */}
      <section className="relative rounded-xl bg-[#161b27] p-6">
        <button
          type="button"
          onClick={onBack}
          className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
        >
          <ArrowLeft size={16} />
          Back
        </button>
        <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
          <div className="flex items-center gap-5">
            <div className="h-32 w-32 shrink-0 overflow-hidden rounded-full ring-2 ring-white/10">
              {artist.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={artist.imageUrl}
                  alt={artist.name}
                  crossOrigin="anonymous"
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-indigo-600 to-slate-800">
                  <span className="text-5xl font-bold text-white/90">{firstLetter}</span>
                </div>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold text-slate-100 text-balance">{artist.name}</h1>
                <button
                  type="button"
                  aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
                  aria-pressed={isFavorite}
                  onClick={onFavoriteToggle}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-white/5 transition-colors hover:bg-white/10"
                >
                  <Star size={18} className={isFavorite ? "fill-yellow-400 text-yellow-400" : "text-slate-400"} />
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${statusClass}`}>
                  {artist.status}
                </span>
                {artist.genres.map((g) => (
                  <span key={g} className="rounded-full bg-white/5 px-2.5 py-0.5 text-xs text-slate-300">
                    {g}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <ScoreRing value={bookingSignals.composite} size={104} stroke={9} color={verdict.ring}>
              <div className="flex flex-col items-center">
                <span className="text-3xl font-bold text-slate-100">{Math.round(bookingSignals.composite)}</span>
                <span className="text-[10px] uppercase tracking-wide text-slate-500">Composite</span>
              </div>
            </ScoreRing>
            <span className={`rounded-full px-3 py-1 text-sm font-semibold ${verdict.className}`}>{verdict.label}</span>
          </div>
        </div>
      </section>

      {/* 2. BOOKING SIGNALS */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-100">Booking Signals</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <SignalBar label="XGBoost Score" weight={40} value={bookingSignals.xgboost} />
          <SignalBar label="Scene Score" weight={35} value={bookingSignals.scene} />
          <SignalBar label="LOFI Fit" weight={25} value={bookingSignals.lofiFit} />
        </div>
        <div className="mt-4 flex items-center justify-between rounded-lg bg-[#1e2535] px-4 py-3">
          <span className="text-sm text-slate-400">Overall Composite</span>
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold text-slate-100">{Math.round(bookingSignals.composite)}</span>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${verdict.className}`}>
              {verdict.label}
            </span>
          </div>
        </div>
      </section>

      {/* 3. MULTI-PLATFORM GROWTH CHART */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Growth — 12 months</h2>
          </div>
          {multiTimeseries.length > 1 && (
            <div className="flex gap-1">
              {multiTimeseries.map(m => (
                <button
                  key={m.platform}
                  type="button"
                  onClick={() => setActivePlatform(m.platform)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    activePlatform === m.platform
                      ? "bg-indigo-500/20 text-indigo-300"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="h-64 w-full">
          {chartData.length === 0 ? (
            <div className="flex h-full w-full items-center justify-center rounded-lg border border-dashed border-white/10 text-sm text-slate-500">
              No data available
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="date" stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} width={52} tickFormatter={v => fmt(v)} />
                <Tooltip
                  contentStyle={{
                    background: "#1e2535",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 8,
                    color: "#f1f5f9",
                  }}
                  labelStyle={{ color: "#94a3b8" }}
                  formatter={(v: number) => [fmt(v)]}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={PLATFORM_COLORS[activePlatform] ?? "#6366f1"}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      {/* 4. TRACKS */}
      {tracks.length > 0 && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <Music2 size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Top Tracks</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-2 pr-4 font-medium">Track</th>
                  <th className="pb-2 pr-4 font-medium">Released</th>
                  <th className="pb-2 pr-4 font-medium text-right">Streams</th>
                  <th className="pb-2 pr-4 font-medium text-right">Pop</th>
                  <th className="pb-2 pr-4 font-medium text-right">Spotify #</th>
                  <th className="pb-2 font-medium text-right">Beatport #</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {tracks.map((t, i) => (
                  <tr key={t.cm_track_id ?? i} className="hover:bg-white/3">
                    <td className="py-2 pr-4 font-medium text-slate-200 max-w-[200px] truncate">{t.track_name ?? "—"}</td>
                    <td className="py-2 pr-4 text-slate-400">{t.release_date ? t.release_date.slice(0, 10) : "—"}</td>
                    <td className="py-2 pr-4 text-right text-slate-300">{fmt(t.spotify_streams)}</td>
                    <td className="py-2 pr-4 text-right text-slate-300">{t.spotify_popularity ?? "—"}</td>
                    <td className="py-2 pr-4 text-right text-slate-300">{t.peak_spotify_chart ?? "—"}</td>
                    <td className="py-2 text-right text-slate-300">{t.peak_beatport_chart ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 5. VALIDATION EVENTS / MILESTONES */}
      {validationEvents.length > 0 && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <CheckCircle2 size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Milestones</h2>
          </div>
          <div className="flex flex-col gap-2">
            {validationEvents.map(ve => (
              <div key={ve.id} className="flex items-start gap-3 rounded-lg bg-[#1e2535] px-4 py-3">
                {ve.confirmed
                  ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-green-400" />
                  : <Circle size={15} className="mt-0.5 shrink-0 text-slate-500" />
                }
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-200 capitalize">{ve.event_type.replace(/_/g, " ")}</p>
                  {ve.source && <p className="text-xs text-slate-500">{ve.source}</p>}
                </div>
                <span className="shrink-0 text-xs text-slate-500">
                  {ve.event_date ? ve.event_date.slice(0, 10) : ""}
                </span>
                {!ve.confirmed && (
                  <span className="shrink-0 rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-400">
                    unconfirmed
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 6. SIMILAR ARTISTS */}
      {similarArtists.length > 0 && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <Users size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Similar Artists</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {similarArtists.map(name => (
              <span
                key={name}
                className="rounded-full bg-[#1e2535] px-3 py-1.5 text-sm text-slate-300 ring-1 ring-white/5"
              >
                {name}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* 7. EVENT TIMELINE */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-6 flex items-center gap-2">
          <Calendar size={18} className="text-indigo-400" />
          <h2 className="text-lg font-semibold text-slate-100">Event Timeline</h2>
        </div>
        {sortedEvents.length === 0 ? (
          <p className="text-sm text-slate-500">No events recorded.</p>
        ) : (
          <div className="relative overflow-x-auto pb-2">
            <div className="relative flex min-w-max items-start gap-12 px-2">
              <div className="absolute left-0 right-0 top-2 h-px bg-white/10" />
              {sortedEvents.map((e, i) => (
                <div key={`${e.venue}-${i}`} className="group relative flex flex-col items-center gap-2">
                  <span
                    className={`relative z-10 h-4 w-4 rounded-full ring-4 ring-[#161b27] ${
                      e.festival ? "bg-indigo-400" : "bg-slate-500"
                    }`}
                  />
                  <span className="text-xs font-medium text-slate-300">{e.venue}</span>
                  <span className="text-[11px] text-slate-500">
                    {new Date(e.date).toLocaleDateString("en-US", { month: "short", year: "numeric" })}
                  </span>
                  <div className="pointer-events-none absolute -top-10 left-1/2 z-20 -translate-x-1/2 whitespace-nowrap rounded-md bg-[#1e2535] px-2 py-1 text-xs text-slate-200 opacity-0 shadow-lg ring-1 ring-white/10 transition-opacity group-hover:opacity-100">
                    {e.attending.toLocaleString()} attending{e.festival ? " · Festival" : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* 8. NOTES PANEL */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-4 flex items-center gap-2">
          <Sparkles size={18} className="text-indigo-400" />
          <h2 className="text-lg font-semibold text-slate-100">Notes</h2>
        </div>
        <div className="flex flex-col gap-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a note about this artist…"
            rows={3}
            className="w-full resize-none rounded-lg bg-[#1e2535] p-3 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleAdd}
              disabled={!draft.trim()}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Add Note
            </button>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3">
          {notes.length === 0 ? (
            <p className="text-sm text-slate-500">No notes yet.</p>
          ) : (
            notes.map((n) => (
              <div key={n.id} className="rounded-lg bg-[#1e2535] p-3">
                <p className="text-sm text-slate-200">{n.text}</p>
                <span className="mt-1 block text-xs text-slate-500">
                  {new Date(n.createdAt).toLocaleString("en-US", {
                    month: "short",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  )
}
