"use client"

import { useState } from "react"
import {
  ArrowLeft,
  Star,
  TrendingUp,
  Calendar,
  Sparkles,
  ChevronDown,
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

export interface ArtistProfileProps {
  artist: { id: string; name: string; imageUrl: string | null; status: string; genres: string[] }
  scores: {
    momentum: number
    growth: number
    marketRelevance: number
    futurePotential: number
    confidence: number
  }
  bookingSignals: { xgboost: number; scene: number; lofiFit: number; composite: number }
  growthData: Array<{ date: string; listeners: number }>
  events: Array<{ date: string; venue: string; attending: number; festival: boolean }>
  notes: Array<{ id: string; text: string; createdAt: string }>
  onAddNote: (text: string) => void
  isFavorite: boolean
  onFavoriteToggle: () => void
  onBack?: () => void
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

function getStrength(value: number): string {
  if (value >= 67) return "Strong"
  if (value >= 40) return "Moderate"
  return "Weak"
}

/* Circular progress ring */
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

const SCORE_META: { key: keyof ArtistProfileProps["scores"]; label: string; sub: string[] }[] = [
  { key: "momentum", label: "Momentum", sub: ["Streaming velocity", "Social mentions", "Playlist adds"] },
  { key: "growth", label: "Growth", sub: ["MoM listener growth", "Follower trend", "Reach expansion"] },
  { key: "marketRelevance", label: "Market Relevance", sub: ["Genre demand", "Territory fit", "Booking density"] },
  { key: "futurePotential", label: "Future Potential", sub: ["Trajectory model", "Breakout signals", "Label momentum"] },
  { key: "confidence", label: "Confidence", sub: ["Data coverage", "Signal agreement", "Sample size"] },
]

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

export default function ArtistProfile({
  artist,
  scores,
  bookingSignals,
  growthData,
  events,
  notes,
  onAddNote,
  isFavorite,
  onFavoriteToggle,
  onBack,
}: ArtistProfileProps) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [draft, setDraft] = useState("")
  const verdict = getVerdict(bookingSignals.composite)
  const firstLetter = artist.name.trim().charAt(0).toUpperCase() || "?"
  const statusClass = STATUS_STYLES[artist.status] ?? STATUS_STYLES.pending

  const sortedEvents = [...events].sort((a, b) => +new Date(a.date) - +new Date(b.date))

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
                  src={artist.imageUrl || "/placeholder.svg"}
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

      {/* 3. FIVE SCORES BREAKDOWN */}
      <section>
        <h2 className="mb-4 text-lg font-semibold text-slate-100">Score Breakdown</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
          {SCORE_META.map(({ key, label, sub }) => {
            const value = scores[key]
            const isOpen = expanded === key
            return (
              <div key={key} className="rounded-xl bg-[#161b27] p-4">
                <button
                  type="button"
                  onClick={() => setExpanded(isOpen ? null : key)}
                  aria-expanded={isOpen}
                  className="flex w-full flex-col items-center gap-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50"
                >
                  <span className="text-sm font-medium text-slate-300">{label}</span>
                  <ScoreRing value={value} size={72}>
                    <span className="text-lg font-bold text-slate-100">{Math.round(value)}</span>
                  </ScoreRing>
                  <span className="flex items-center gap-1 text-xs text-slate-400">
                    {getStrength(value)}
                    <ChevronDown size={14} className={isOpen ? "rotate-180 transition-transform" : "transition-transform"} />
                  </span>
                </button>
                {isOpen && (
                  <div className="mt-3 flex flex-col gap-1 border-t border-white/5 pt-3">
                    {sub.map((s, si) => (
                      <div key={s} className="flex items-center justify-between text-xs">
                        <span className="text-slate-400">{s}</span>
                        <span className="text-slate-300">
                          {Math.round(Math.max(0, Math.min(100, value + (si - 1) * 6)))}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* 4. GROWTH CHART */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-4 flex items-center gap-2">
          <TrendingUp size={18} className="text-indigo-400" />
          <h2 className="text-lg font-semibold text-slate-100">Spotify Monthly Listeners — 12 months</h2>
        </div>
        <div className="h-64 w-full">
          {growthData.length === 0 ? (
            <div className="flex h-full w-full items-center justify-center rounded-lg border border-dashed border-white/10 text-sm text-slate-500">
              No listener data available
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={growthData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="date" stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} width={48} />
                <Tooltip
                  contentStyle={{
                    background: "#1e2535",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 8,
                    color: "#f1f5f9",
                  }}
                  labelStyle={{ color: "#94a3b8" }}
                />
                <Line type="monotone" dataKey="listeners" stroke="#6366f1" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      {/* 5. MILESTONE STRIP */}
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
              {/* timeline line */}
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
                  {/* hover tooltip */}
                  <div className="pointer-events-none absolute -top-10 left-1/2 z-20 -translate-x-1/2 whitespace-nowrap rounded-md bg-[#1e2535] px-2 py-1 text-xs text-slate-200 opacity-0 shadow-lg ring-1 ring-white/10 transition-opacity group-hover:opacity-100">
                    {e.attending.toLocaleString()} attending{e.festival ? " · Festival" : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* 6. NOTES PANEL */}
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
