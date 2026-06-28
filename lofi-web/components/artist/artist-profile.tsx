"use client"

import { useMemo, useState, useEffect, useCallback } from "react"
import {
  ArrowLeft, Star, TrendingUp, Calendar, Sparkles,
  Music2, Users, CheckCircle2, Circle, MapPin, Building2,
  ExternalLink, Globe, Disc3, MessageSquare,
  Flame, Target, BarChart2, AlertTriangle, Lightbulb, Activity,
  RefreshCw, Tag, Trash2, ChevronDown,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar, Cell,
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
} from "recharts"
import type { TrackRow, ValidationEventRow, MultiTimeseriesItem } from "@/types/supabase"

function fmt(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—"
  if (n >= 999_500) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}K`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(Math.round(n))
}

const DOMAIN_LABELS: Record<string, { label: string; color: string }> = {
  spotify: { label: "Spotify", color: "#1DB954" },
  instagram: { label: "Instagram", color: "#E1306C" },
  soundcloud: { label: "SoundCloud", color: "#FF5500" },
  tiktok: { label: "TikTok", color: "#69C9D0" },
  youtube: { label: "YouTube", color: "#FF0000" },
  resident_advisor: { label: "RA", color: "#6366f1" },
  ra: { label: "RA", color: "#6366f1" },
  beatport: { label: "Beatport", color: "#00A0C6" },
  lastfm: { label: "Last.fm", color: "#D51007" },
  facebook: { label: "Facebook", color: "#1877F2" },
}

export interface ArtistProfileProps {
  artist: {
    id: string; name: string; imageUrl: string | null; status: string; genres: string[]
    description?: string | null
    recordLabel?: string | null
    bookingAgent?: string | null
    currentCity?: string | null
    hometownCity?: string | null
  }
  bookingSignals: { xgboost: number; scene: number; lofiFit: number; composite: number }
  growthData: Array<{ date: string; listeners: number }>
  multiTimeseries: MultiTimeseriesItem[]
  events: Array<{ date: string; venue: string; attending: number; festival: boolean; city?: string; country?: string }>
  notes: Array<{ id: string; text: string; createdAt: string; noteType?: string }>
  onAddNote: (text: string, noteType?: string) => void
  isFavorite: boolean
  onFavoriteToggle: () => void
  onBack?: () => void
  tracks: TrackRow[]
  validationEvents: ValidationEventRow[]
  similarArtists: string[]
  socialLinks?: { url: string[]; domain: string }[]
  fanCities?: { city: string; country: string; count?: number; pct?: number }[]
  noteworthy?: { title?: string; description?: string; value?: string }[]
  pfFans?: number | null
  pfTotalPerformances?: number | null
  pfUpcomingPerformances?: number | null
  pfGenres?: string[] | null
  instagramAudience?: Record<string, unknown> | null
  xgboostGrowth90d?: number | null
  xgboostMissingDataPct?: number | null
  albums?: { name: string; release_date?: string; image_url?: string; type?: string }[]
  cmArtistScore?: number | null
  cmArtistRank?: number | null
  spMonthlyListeners?: number | null
  igFollowers?: number | null
  tiktokFollowers?: number | null
  lfmListeners?: number | null
  fiveScores?: {
    momentum: number; growth: number; market_relevance: number
    future_potential: number; confidence: number
    breakdown: { sp_30d_pct: number | null; sp_90d_pct: number | null; accel: number | null; cross_platform_30d: number | null; platforms_growing: number | null; data_filled: number; data_total: number }
  } | null
  mlFeatures?: Record<string, number | null> | null
  playlists?: { platform: string; playlist_name: string; playlist_followers: number | null; position: number | null; added_at: string | null }[]
  beatportChartEntries?: { genre: string | null; chart_position: number | null; track_name: string | null; scraped_at: string }[]
  traxsourceChartEntries?: { genre: string | null; chart_position: number | null; track_name: string | null; scraped_at: string | null }[]
  pfEvents?: Record<string, unknown>[]
  tiktokAudience?: Record<string, unknown> | null
  milestones?: Record<string, unknown>[] | null
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

function ScoreRing({ value, size = 64, stroke = 6, color = "#6366f1", children }: {
  value: number; size?: number; stroke?: number; color?: string; children?: React.ReactNode
}) {
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (Math.max(0, Math.min(100, value)) / 100) * circumference
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={radius} stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset} fill="none" />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center">{children}</span>
    </div>
  )
}

function scoreInterpret(key: string, v: number): { label: string; color: string } {
  if (key === 'momentum') {
    if (v >= 70) return { label: "Streaming buzz is growing fast", color: "text-emerald-400" }
    if (v >= 45) return { label: "Steady audience growth", color: "text-indigo-400" }
    if (v >= 25) return { label: "Growth slowing or flat", color: "text-amber-400" }
    return { label: "Declining or no data", color: "text-slate-500" }
  }
  if (key === 'growth') {
    if (v >= 70) return { label: "Rapidly accelerating", color: "text-emerald-400" }
    if (v >= 45) return { label: "Picking up momentum", color: "text-indigo-400" }
    if (v >= 25) return { label: "Moderate, not yet breaking", color: "text-amber-400" }
    return { label: "Stagnant or declining", color: "text-slate-500" }
  }
  if (key === 'market_relevance') {
    if (v >= 70) return { label: "Established, sizeable fanbase", color: "text-emerald-400" }
    if (v >= 45) return { label: "Mid-size, building presence", color: "text-indigo-400" }
    if (v >= 25) return { label: "Emerging artist", color: "text-amber-400" }
    return { label: "Very early stage", color: "text-slate-500" }
  }
  if (key === 'future_potential') {
    if (v >= 70) return { label: "Strong 6–12 month outlook", color: "text-emerald-400" }
    if (v >= 45) return { label: "Promising trajectory", color: "text-indigo-400" }
    if (v >= 25) return { label: "Uncertain next steps", color: "text-amber-400" }
    return { label: "Low near-term potential", color: "text-slate-500" }
  }
  if (v >= 70) return { label: "Rich data — high confidence", color: "text-emerald-400" }
  if (v >= 45) return { label: "Adequate data coverage", color: "text-indigo-400" }
  if (v >= 25) return { label: "Limited data available", color: "text-amber-400" }
  return { label: "Insufficient data", color: "text-slate-500" }
}

const SCORE_DIMS: { key: 'momentum' | 'growth' | 'market_relevance' | 'future_potential' | 'confidence'; label: string; Icon: LucideIcon; radarLabel: string }[] = [
  { key: 'momentum',         label: 'Current Buzz',    Icon: Flame,     radarLabel: 'Buzz' },
  { key: 'growth',           label: 'Acceleration',    Icon: TrendingUp, radarLabel: 'Accel' },
  { key: 'market_relevance', label: 'Audience Size',   Icon: Users,     radarLabel: 'Size' },
  { key: 'future_potential', label: '6-Month Outlook', Icon: Target,    radarLabel: 'Outlook' },
  { key: 'confidence',       label: 'Data Quality',    Icon: BarChart2, radarLabel: 'Data' },
]

function ScoreRadar({ fiveScores }: {
  fiveScores: { momentum: number; growth: number; market_relevance: number; future_potential: number; confidence: number }
}) {
  const radarData = SCORE_DIMS.map(d => ({ axis: d.radarLabel, value: Math.round(fiveScores[d.key]) }))
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
      <div className="flex shrink-0 items-center justify-center">
        <ResponsiveContainer width={200} height={200}>
          <RadarChart data={radarData} margin={{ top: 10, right: 28, bottom: 10, left: 28 }}>
            <PolarGrid stroke="rgba(255,255,255,0.08)" />
            <PolarAngleAxis dataKey="axis" tick={{ fill: '#94a3b8', fontSize: 11 }} />
            <Radar dataKey="value" stroke="#6366f1" fill="#6366f1" fillOpacity={0.25} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-1 flex-col gap-2">
        {SCORE_DIMS.map(({ key, label, Icon }) => {
          const v = fiveScores[key]
          const { label: interp, color } = scoreInterpret(key, v)
          return (
            <div key={key} className="flex items-center gap-3 rounded-lg bg-[#1e2535] px-3 py-2">
              <Icon size={14} className="shrink-0 text-indigo-400" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-1">
                  <span className="text-xs font-medium text-slate-300">{label}</span>
                  <span className="text-xs font-bold text-slate-100">{Math.round(v)}</span>
                </div>
                <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-indigo-500/70 transition-all" style={{ width: `${Math.max(0, Math.min(100, v))}%` }} />
                </div>
                <p className={`mt-0.5 text-[11px] leading-tight ${color}`}>{interp}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function signalLabel(value: number): { text: string; color: string } {
  if (value >= 70) return { text: "Strong",   color: "text-emerald-400" }
  if (value >= 50) return { text: "Moderate", color: "text-indigo-400" }
  if (value >= 30) return { text: "Low",      color: "text-amber-400" }
  return { text: "Weak", color: "text-slate-500" }
}

function SignalBar({ label, weight, value, explanation }: { label: string; weight: number; value: number; explanation: string }) {
  const sig = signalLabel(value)
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-[#1e2535] p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-200">{label}</span>
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-400">{weight}% weight</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-indigo-400"
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
      <span className={`text-lg font-semibold ${sig.color}`}>{sig.text}</span>
      <p className="text-xs leading-relaxed text-slate-500">{explanation}</p>
    </div>
  )
}

function pctFmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "Unavailable"
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`
}

function milestoneText(m: Record<string, unknown>): string {
  return String(m.title ?? m.name ?? m.type ?? m.event_type ?? m.milestone ?? "Milestone")
    .replace(/_/g, " ")
}

function milestoneDate(m: Record<string, unknown>): string {
  return String(m.date ?? m.event_date ?? m.achieved_at ?? m.detected_at ?? "").slice(0, 10)
}

function milestoneSource(m: Record<string, unknown>): string {
  return String(m.source ?? m.platform ?? m.url ?? m.event_url ?? m.venue ?? "Chartmetric")
}

const PLATFORM_COLORS: Record<string, string> = {
  spotify: "#1DB954", instagram: "#E1306C", tiktok: "#69C9D0", soundcloud: "#FF5500",
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  first_ibiza: "First Ibiza Booking",
  boiler_room: "Boiler Room",
  first_all_night_long: "First All-Night-Long",
  first_headline_500: "First Headline (500+)",
  first_headline_1k: "First Headline (1K+)",
  first_headline_5k: "First Headline (5K+)",
  ra_podcast: "RA Podcast Feature",
  festival_main_stage: "Festival Main Stage",
  major_label_signing: "Major Label Signing",
  agency_signing: "Agency Signing",
}

const GENRE_LABELS: Record<string, string> = {
  'tech-house': 'Tech House', 'house': 'House', 'melodic-house-techno': 'Melodic H&T',
  'techno-peak-time-driving': 'Techno', 'minimal-deep-tech': 'Minimal',
  'afro-house': 'Afro House', 'organic-house-downtempo': 'Organic',
  'progressive-house': 'Progressive', 'deep-house': 'Deep House', 'nu-disco-indie-dance': 'Nu Disco',
}

function ShowHistoryTabs({ raEvents, pfEvents, beatportChartEntries, traxsourceChartEntries }: {
  raEvents: { date: string; venue: string; attending: number; festival: boolean; city?: string; country?: string }[]
  pfEvents: Record<string, unknown>[]
  beatportChartEntries: { genre: string | null; chart_position: number | null; track_name: string | null; scraped_at: string }[]
  traxsourceChartEntries: { genre: string | null; chart_position: number | null; track_name: string | null; scraped_at: string | null }[]
}) {
  const [tab, setTab] = useState<'ra' | 'partyflock' | 'charts'>('ra')
  const hasPf = pfEvents.length > 0
  const hasCharts = beatportChartEntries.length > 0 || traxsourceChartEntries.length > 0

  const yearlyData = useMemo(() => {
    const byYear: Record<string, { year: string; total: number; nl: number }> = {}
    for (const e of raEvents) {
      const year = e.date?.slice(0, 4)
      if (!year || year.length !== 4) continue
      if (!byYear[year]) byYear[year] = { year, total: 0, nl: 0 }
      byYear[year].total++
      if (e.country === 'NL' || e.country === 'Netherlands') byYear[year].nl++
    }
    return Object.values(byYear).sort((a, b) => a.year.localeCompare(b.year)).slice(-6)
  }, [raEvents])

  const maxBookings = Math.max(...yearlyData.map(d => d.total), 1)

  return (
    <div>
      {/* Year-by-year booking growth */}
      {yearlyData.length >= 2 && (
        <div className="mb-5 rounded-lg bg-[#1e2535] p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Booking Activity — Year on Year</p>
          <div className="flex h-24 items-end gap-2">
            {yearlyData.map((d, i) => {
              const prev = yearlyData[i - 1]
              const growth = prev && prev.total > 0 ? Math.round(((d.total - prev.total) / prev.total) * 100) : null
              const barPct = Math.round((d.total / maxBookings) * 100)
              const isLatest = i === yearlyData.length - 1
              return (
                <div key={d.year} className="flex flex-1 flex-col items-center gap-1">
                  {growth != null ? (
                    <span className={`text-[10px] font-bold ${growth > 0 ? 'text-emerald-400' : growth < 0 ? 'text-rose-400' : 'text-slate-500'}`}>
                      {growth > 0 ? '+' : ''}{growth}%
                    </span>
                  ) : <span className="text-[10px] text-transparent">0%</span>}
                  <div
                    className="w-full rounded-t transition-all"
                    style={{
                      height: `${Math.max(barPct, d.total > 0 ? 8 : 0)}%`,
                      background: isLatest ? 'linear-gradient(to top, #6366f1, #818cf8)' : 'rgba(99,102,241,0.35)',
                      minHeight: d.total > 0 ? 4 : 0,
                    }}
                  />
                  <div className="text-center">
                    <p className="text-xs font-bold text-slate-100">{d.total}</p>
                    <p className="text-[9px] text-slate-500">{d.year}</p>
                  </div>
                </div>
              )
            })}
          </div>
          <p className="mt-2 text-[10px] text-slate-600">Shows per year · Resident Advisor data</p>
        </div>
      )}

      <div className="mb-4 flex gap-1 rounded-lg bg-[#1e2535] p-1 w-fit">
        <button type="button" onClick={() => setTab('ra')}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${tab === 'ra' ? 'bg-[#161b27] text-slate-200 shadow' : 'text-slate-500 hover:text-slate-300'}`}>
          Resident Advisor ({raEvents.length})
        </button>
        {hasPf && (
          <button type="button" onClick={() => setTab('partyflock')}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${tab === 'partyflock' ? 'bg-[#161b27] text-slate-200 shadow' : 'text-slate-500 hover:text-slate-300'}`}>
            Partyflock NL ({pfEvents.length})
          </button>
        )}
        {hasCharts && (
          <button type="button" onClick={() => setTab('charts')}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${tab === 'charts' ? 'bg-[#161b27] text-slate-200 shadow' : 'text-slate-500 hover:text-slate-300'}`}>
            Charts ({beatportChartEntries.length + traxsourceChartEntries.length})
          </button>
        )}
      </div>
      {tab === 'ra' && (
        raEvents.length === 0 ? (
          <p className="text-sm text-slate-500">No RA events recorded.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-2 pr-4 font-medium">Date</th>
                  <th className="pb-2 pr-4 font-medium">Venue</th>
                  <th className="pb-2 pr-4 font-medium">City</th>
                  <th className="pb-2 font-medium">Country</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {raEvents.slice(0, 50).map((e, i) => (
                  <tr key={i} className="hover:bg-white/[0.02]">
                    <td className="py-2 pr-4 text-slate-400">{e.date?.slice(0, 10)}</td>
                    <td className="py-2 pr-4 font-medium text-slate-200">{e.venue}</td>
                    <td className="py-2 pr-4 text-slate-400">{e.city ?? '—'}</td>
                    <td className="py-2 text-slate-400">{e.country ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
      {tab === 'partyflock' && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="pb-2 pr-4 font-medium">Date</th>
                <th className="pb-2 pr-4 font-medium">Event</th>
                <th className="pb-2 pr-4 font-medium">Venue</th>
                <th className="pb-2 font-medium">City</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {pfEvents.slice(0, 50).map((e, i) => (
                <tr key={i} className="hover:bg-white/[0.02]">
                  <td className="py-2 pr-4 text-slate-400">{String(e.start_date ?? e.date ?? '—').slice(0, 10)}</td>
                  <td className="py-2 pr-4 font-medium text-slate-200">{String(e.name ?? e.title ?? '—')}</td>
                  <td className="py-2 pr-4 text-slate-400">{String(e.venue ?? '—')}</td>
                  <td className="py-2 text-slate-400">{String(e.city ?? '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab === 'charts' && (
        <div className="flex flex-col gap-6">
          {beatportChartEntries.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-slate-300">Beatport</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="pb-2 pr-4 font-medium">Genre</th>
                      <th className="pb-2 pr-4 font-medium text-right">Position</th>
                      <th className="pb-2 pr-4 font-medium">Track</th>
                      <th className="pb-2 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {beatportChartEntries.map((e, i) => (
                      <tr key={i} className="hover:bg-white/[0.02]">
                        <td className="py-2 pr-4 text-slate-400">{GENRE_LABELS[e.genre ?? ''] ?? e.genre ?? '—'}</td>
                        <td className="py-2 pr-4 text-right font-bold text-orange-400">#{e.chart_position ?? '?'}</td>
                        <td className="py-2 pr-4 text-slate-300 max-w-[180px] truncate">{e.track_name ?? '—'}</td>
                        <td className="py-2 text-slate-500">{e.scraped_at?.slice(0, 10) ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {traxsourceChartEntries.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-slate-300">Traxsource</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="pb-2 pr-4 font-medium">Genre</th>
                      <th className="pb-2 pr-4 font-medium text-right">Position</th>
                      <th className="pb-2 pr-4 font-medium">Track</th>
                      <th className="pb-2 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {traxsourceChartEntries.map((e, i) => (
                      <tr key={i} className="hover:bg-white/[0.02]">
                        <td className="py-2 pr-4 text-slate-400">{GENRE_LABELS[e.genre ?? ''] ?? e.genre ?? '—'}</td>
                        <td className="py-2 pr-4 text-right font-bold text-cyan-400">#{e.chart_position ?? '?'}</td>
                        <td className="py-2 pr-4 text-slate-300 max-w-[180px] truncate">{e.track_name ?? '—'}</td>
                        <td className="py-2 text-slate-500">{e.scraped_at?.slice(0, 10) ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TracksTabs({ tracks, playlists }: { tracks: TrackRow[]; playlists: { platform: string; playlist_name: string; playlist_followers: number | null; position: number | null; added_at: string | null }[] }) {
  const [tab, setTab] = useState<'tracks' | 'playlists'>('tracks')
  return (
    <div>
      <div className="mb-4 flex gap-1 rounded-lg bg-[#1e2535] p-1 w-fit">
        {(['tracks', 'playlists'] as const).map(t => (
          <button key={t} type="button" onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${tab === t ? 'bg-[#161b27] text-slate-200 shadow' : 'text-slate-500 hover:text-slate-300'}`}>
            {t} {t === 'tracks' ? `(${tracks.length})` : `(${playlists.length})`}
          </button>
        ))}
      </div>
      {tab === 'tracks' ? (
        tracks.length === 0 ? (
          <p className="text-sm text-slate-500">No tracks found.</p>
        ) : (
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
                  <tr key={t.cm_track_id ?? i} className="hover:bg-white/[0.02]">
                    <td className="py-2 pr-4 font-medium text-slate-200 max-w-[200px] truncate">{t.track_name ?? "—"}</td>
                    <td className="py-2 pr-4 text-slate-400">{t.release_date ? String(t.release_date).slice(0, 10) : "—"}</td>
                    <td className="py-2 pr-4 text-right text-slate-300">{fmt(t.spotify_streams)}</td>
                    <td className="py-2 pr-4 text-right text-slate-300">{t.spotify_popularity ?? "—"}</td>
                    <td className="py-2 pr-4 text-right text-slate-300">{t.peak_spotify_chart ?? "—"}</td>
                    <td className="py-2 text-right text-slate-300">{t.peak_beatport_chart ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        playlists.length === 0 ? (
          <p className="text-sm text-slate-500">No playlist placements found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-2 pr-4 font-medium">Platform</th>
                  <th className="pb-2 pr-4 font-medium">Playlist</th>
                  <th className="pb-2 pr-4 font-medium text-right">Followers</th>
                  <th className="pb-2 pr-4 font-medium text-right">Pos</th>
                  <th className="pb-2 font-medium">Added</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {playlists.map((p, i) => (
                  <tr key={i} className="hover:bg-white/[0.02]">
                    <td className="py-2 pr-4 text-slate-400 capitalize">{p.platform ?? "—"}</td>
                    <td className="py-2 pr-4 font-medium text-slate-200 max-w-[200px] truncate">{p.playlist_name ?? "—"}</td>
                    <td className="py-2 pr-4 text-right text-slate-300">{fmt(p.playlist_followers)}</td>
                    <td className="py-2 pr-4 text-right text-slate-300">{p.position ?? "—"}</td>
                    <td className="py-2 text-slate-400">{p.added_at ? String(p.added_at).slice(0, 10) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}

export default function ArtistProfile({
  artist, bookingSignals, growthData, multiTimeseries, events, notes,
  onAddNote, isFavorite, onFavoriteToggle, onBack,
  tracks, validationEvents, similarArtists,
  socialLinks = [], fanCities = [], noteworthy = [],
  pfFans, pfTotalPerformances, pfUpcomingPerformances, pfGenres,
  instagramAudience, xgboostGrowth90d, xgboostMissingDataPct, albums = [],
  cmArtistScore, cmArtistRank, spMonthlyListeners, igFollowers, tiktokFollowers, lfmListeners,
  fiveScores, mlFeatures, playlists = [], beatportChartEntries = [], traxsourceChartEntries = [],
  pfEvents = [], tiktokAudience: _tiktokAudience, milestones = null,
}: ArtistProfileProps) {
  const [draft, setDraft] = useState("")
  const [noteType, setNoteType] = useState<'performance' | 'correction' | 'intel'>('performance')
  const [activePlatform, setActivePlatform] = useState<string>(multiTimeseries[0]?.platform ?? "spotify")
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null)
  const [schedulingDelete, setSchedulingDelete] = useState(false)
  const [monitorGroups, setMonitorGroups] = useState<{ id: string; name: string; color: string }[]>([])
  const [artistGroups, setArtistGroups] = useState<string[]>([]) // group ids this artist is in
  const [groupMenuOpen, setGroupMenuOpen] = useState(false)
  const [groupsLoading, setGroupsLoading] = useState(false)

  // Load monitoring groups
  const loadGroups = useCallback(async () => {
    setGroupsLoading(true)
    try {
      const [allRes, memberRes] = await Promise.all([
        fetch('/api/monitor-groups'),
        fetch(`/api/artists/${artist.id}/monitor`),
      ])
      const all = await allRes.json()
      const memberships = await memberRes.json()
      setMonitorGroups((all ?? []).map((g: { id: string; name: string; color: string }) => ({ id: g.id, name: g.name, color: g.color })))
      setArtistGroups((memberships ?? []).map((m: { group_id: string }) => m.group_id))
    } finally {
      setGroupsLoading(false)
    }
  }, [artist.id])

  useEffect(() => { loadGroups() }, [loadGroups])

  async function handleRefreshScores() {
    setRefreshing(true)
    setRefreshMsg(null)
    try {
      const res = await fetch(`/api/artists/${artist.id}/refresh`, { method: 'POST' })
      const data = await res.json()
      setRefreshMsg(res.ok ? 'Scores refreshed.' : (data.error ?? 'Refresh failed'))
    } finally {
      setRefreshing(false)
    }
  }

  async function toggleMonitorGroup(groupId: string) {
    const inGroup = artistGroups.includes(groupId)
    await fetch(`/api/monitor-groups/${groupId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ artist_id: artist.id, action: inGroup ? 'remove' : 'add' }),
    })
    setArtistGroups(prev => inGroup ? prev.filter(id => id !== groupId) : [...prev, groupId])
  }

  async function handleScheduleDelete() {
    if (!confirm(`Schedule ${artist.name} for deletion? This marks them as excluded and queues permanent removal.`)) return
    setSchedulingDelete(true)
    try {
      await fetch('/api/admin/schedule-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artist_id: artist.id, reason: 'Manual: AI outlier verdict' }),
      })
    } finally {
      setSchedulingDelete(false)
    }
  }
  const verdict = getVerdict(bookingSignals.composite)
  const firstLetter = artist.name.trim().charAt(0).toUpperCase() || "?"
  const statusClass = STATUS_STYLES[artist.status] ?? STATUS_STYLES.pending
  const sortedEvents = [...events].sort((a, b) => +new Date(a.date) - +new Date(b.date))
  const nlEvents = events.filter(e => e.country === 'NL' || e.country === 'Netherlands' || e.city?.toLowerCase().includes('amsterdam'))

  const activeTs = multiTimeseries.find(m => m.platform === activePlatform)
  const rawChartData = activeTs
    ? activeTs.data.map(p => ({ date: p.date.slice(0, 7), value: p.value }))
    : growthData.map(p => ({ date: p.date.slice(0, 7), value: p.listeners }))

  const chartData: { date: string; value?: number }[] = rawChartData
  const xgbLabel = xgboostGrowth90d == null
    ? { text: "No model forecast", color: "text-slate-500", bg: "bg-slate-500/10" }
    : xgboostGrowth90d >= 15
    ? { text: "Breakout signal", color: "text-emerald-400", bg: "bg-emerald-500/10" }
    : xgboostGrowth90d >= 5
    ? { text: "Positive trend", color: "text-indigo-400", bg: "bg-indigo-500/10" }
    : xgboostGrowth90d >= -5
    ? { text: "Stable", color: "text-slate-400", bg: "bg-slate-500/10" }
    : { text: "Cooling", color: "text-rose-400", bg: "bg-rose-500/10" }
  const cmMilestones = (milestones ?? []).filter(Boolean)

  // Social links: filter to known platforms, deduplicate
  const knownLinks = socialLinks.filter(l => DOMAIN_LABELS[l.domain] && l.url?.length)

  // Fan cities: top 10
  const topCities = [...fanCities].sort((a, b) => (b.pct ?? b.count ?? 0) - (a.pct ?? a.count ?? 0)).slice(0, 10)

  // Instagram audience top countries
  interface CountryAudience { code: string; name: string; percent: string | number; followers: number }
  const igTopCountries = ((instagramAudience?.top_countries ?? []) as CountryAudience[]).slice(0, 8)

  function handleAdd() {
    const text = draft.trim()
    if (!text) return
    onAddNote(text, noteType)
    setDraft("")
  }

  return (
    <div className="flex flex-col gap-6">
      {/* 1. HERO STRIP */}
      <section className="relative rounded-xl bg-[#161b27] p-6">
        <button type="button" onClick={onBack}
          className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200">
          <ArrowLeft size={16} /> Back
        </button>
        <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
          <div className="flex items-center gap-5">
            <div className="h-32 w-32 shrink-0 overflow-hidden rounded-full ring-2 ring-white/10">
              {artist.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={artist.imageUrl} alt={artist.name} crossOrigin="anonymous"
                  className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-indigo-600 to-slate-800">
                  <span className="text-5xl font-bold text-white/90">{firstLetter}</span>
                </div>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold text-slate-100 text-balance">{artist.name}</h1>
                <button type="button" aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
                  aria-pressed={isFavorite} onClick={onFavoriteToggle}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-white/5 transition-colors hover:bg-white/10">
                  <Star size={18} className={isFavorite ? "fill-yellow-400 text-yellow-400" : "text-slate-400"} />
                </button>
              </div>

              {/* Status + genres */}
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${statusClass}`}>
                  {artist.status}
                </span>
                {artist.genres.map(g => (
                  <span key={g} className="rounded-full bg-white/5 px-2.5 py-0.5 text-xs text-slate-300">{g}</span>
                ))}
              </div>

              {/* Meta row: city, label, agent */}
              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                {(artist.currentCity ?? artist.hometownCity) && (
                  <span className="flex items-center gap-1">
                    <MapPin size={12} />{artist.currentCity ?? artist.hometownCity}
                  </span>
                )}
                {artist.recordLabel && (
                  <span className="flex items-center gap-1">
                    <Disc3 size={12} />{artist.recordLabel}
                  </span>
                )}
                {artist.bookingAgent && (
                  <span className="flex items-center gap-1">
                    <Building2 size={12} />{artist.bookingAgent}
                  </span>
                )}
              </div>

              {/* Social links */}
              {knownLinks.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {knownLinks.map(link => {
                    const meta = DOMAIN_LABELS[link.domain]
                    const href = link.url[0]
                    return (
                      <a key={link.domain} href={href} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-opacity hover:opacity-80"
                        style={{ borderColor: meta.color + '40', color: meta.color, background: meta.color + '10' }}>
                        <ExternalLink size={10} />{meta.label}
                      </a>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4">
            <ScoreRing value={bookingSignals.composite} size={104} stroke={9} color={verdict.ring}>
              <div className="flex flex-col items-center gap-0.5 px-1 text-center">
                <span className={`text-xs font-bold leading-tight ${verdict.className.replace(/bg-[^\s]+\s/, '')}`}>{verdict.label}</span>
                <span className="text-[9px] uppercase tracking-wide text-slate-500">AI verdict</span>
              </div>
            </ScoreRing>
          </div>
        </div>

        {/* Bio */}
        {artist.description && (
          <p className="mt-4 border-t border-white/5 pt-4 text-sm leading-relaxed text-slate-400 line-clamp-3">
            {artist.description}
          </p>
        )}
      </section>

      {/* ACTION BAR */}
      <section className="flex flex-wrap items-center gap-2 rounded-xl bg-[#161b27] px-4 py-3">
        {/* Refresh scores */}
        <button type="button" onClick={handleRefreshScores} disabled={refreshing}
          className="flex items-center gap-1.5 rounded-lg bg-[#1e2535] px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-[#2a3347] transition-colors disabled:opacity-50">
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
          {refreshing ? 'Refreshing…' : 'Refresh scores'}
        </button>

        {/* Monitor group dropdown */}
        <div className="relative">
          <button type="button" onClick={() => setGroupMenuOpen(v => !v)}
            className="flex items-center gap-1.5 rounded-lg bg-[#1e2535] px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-[#2a3347] transition-colors">
            <Tag size={12} />
            {artistGroups.length > 0 ? `In ${artistGroups.length} group${artistGroups.length > 1 ? 's' : ''}` : 'Add to group'}
            <ChevronDown size={11} className="opacity-60" />
          </button>
          {groupMenuOpen && (
            <div className="absolute left-0 top-full z-20 mt-1 w-52 overflow-hidden rounded-xl border border-[#1e2535] bg-[#161b27] shadow-2xl">
              {groupsLoading ? (
                <p className="px-3 py-2 text-xs text-slate-500">Loading…</p>
              ) : monitorGroups.length === 0 ? (
                <p className="px-3 py-3 text-xs text-slate-500">No groups — create one in Watchlist</p>
              ) : (
                monitorGroups.map(g => {
                  const inGroup = artistGroups.includes(g.id)
                  return (
                    <button key={g.id} type="button" onClick={() => toggleMonitorGroup(g.id)}
                      className="flex w-full items-center gap-2.5 px-3 py-2 text-xs transition-colors hover:bg-[#1e2535]">
                      <span className="size-2.5 shrink-0 rounded-full" style={{ background: g.color }} />
                      <span className={`flex-1 text-left ${inGroup ? 'font-semibold text-slate-100' : 'text-slate-400'}`}>{g.name}</span>
                      {inGroup && <CheckCircle2 size={12} className="text-emerald-400" />}
                    </button>
                  )
                })
              )}
            </div>
          )}
        </div>

        {/* Schedule for deletion */}
        <button type="button" onClick={handleScheduleDelete} disabled={schedulingDelete}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40 ml-auto">
          <Trash2 size={12} />
          {schedulingDelete ? 'Scheduling…' : 'Schedule deletion'}
        </button>

        {refreshMsg && (
          <span className="ml-2 text-xs text-emerald-400">{refreshMsg}</span>
        )}
      </section>

      {/* PLATFORM STATS ROW */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
          {[
            { label: "CM Score", value: cmArtistScore != null ? cmArtistScore.toFixed(1) : "—" },
            { label: "CM Rank", value: cmArtistRank != null ? `#${cmArtistRank.toLocaleString()}` : "—" },
            { label: "SP Listeners", value: fmt(spMonthlyListeners) },
            { label: "Instagram", value: fmt(igFollowers) },
            { label: "TikTok", value: fmt(tiktokFollowers) },
            { label: "Last.fm", value: fmt(lfmListeners) },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-lg bg-[#1e2535] p-3">
              <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
              <p className="mt-1 text-lg font-bold text-slate-100">{value}</p>
            </div>
          ))}
        </div>
      </section>

      {/* SCORE RADAR */}
      {fiveScores && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-100">Artist Profile</h2>
              <p className="text-xs text-slate-500">What the data says — in booking terms</p>
            </div>
            {fiveScores.breakdown && (
              <span className="text-xs text-slate-500">
                {fiveScores.breakdown.data_filled}/{fiveScores.breakdown.data_total} data points
              </span>
            )}
          </div>
          <ScoreRadar fiveScores={fiveScores} />
        </section>
      )}

      {/* 2. BOOKING SIGNALS */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-100">Booking Signals</h2>
        <div className="mb-4 rounded-lg border border-indigo-500/20 bg-indigo-500/5 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-indigo-300">XGBoost target</p>
              <h3 className="mt-1 text-base font-semibold text-slate-100">Predicted Chartmetric CPP score movement</h3>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">
                This model predicts 90-day CPP growth, not Spotify listeners. CPP is the Chartmetric industry-presence score and is the forecast target carried over from the Streamlit baseline.
              </p>
            </div>
            <div className="shrink-0 rounded-lg bg-[#101521] px-4 py-3 text-right">
              <p className={`text-2xl font-bold ${xgbLabel.color}`}>{pctFmt(xgboostGrowth90d)}</p>
              <p className={`mt-1 rounded-full px-2 py-0.5 text-xs font-medium ${xgbLabel.bg} ${xgbLabel.color}`}>{xgbLabel.text}</p>
              {xgboostMissingDataPct != null && (
                <p className="mt-1 text-[10px] text-slate-500">{xgboostMissingDataPct.toFixed(0)}% model inputs missing</p>
              )}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <SignalBar
            label="Trend Forecast"
            weight={40}
            value={bookingSignals.xgboost}
            explanation="Maps predicted CPP growth onto a 0-100 score: 50 is flat, above 50 is expected growth, below 50 is cooling."
          />
          <SignalBar
            label="Scene Evidence"
            weight={35}
            value={bookingSignals.scene}
            explanation="Combines confirmed milestones, NL/Amsterdam presence, and RA booking history."
          />
          <SignalBar
            label="LOFI Fit"
            weight={25}
            value={bookingSignals.lofiFit}
            explanation="Checks whether the artist matches LOFI's sound, audience, and booking taste. It is suitability, not trend."
          />
        </div>
        <div className="mt-4 flex items-center justify-between rounded-lg bg-[#1e2535] px-4 py-3">
          <span className="text-sm text-slate-400">Overall assessment</span>
          <span className={`rounded-full px-3 py-1 text-sm font-semibold ${verdict.className}`}>{verdict.label}</span>
        </div>
      </section>

      {/* BOOKER INTELLIGENCE */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-1 flex items-center gap-2">
          <MessageSquare size={18} className="text-indigo-400" />
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Booker Intelligence</h2>
            <p className="text-xs text-slate-500">Log real-world observations — they feed back into the model</p>
          </div>
        </div>

        {/* Type selector */}
        <div className="mb-3 mt-4 flex flex-wrap gap-1">
          {([
            { type: 'performance', Icon: Activity,      label: 'Live feedback' },
            { type: 'correction',  Icon: AlertTriangle, label: 'Score correction' },
            { type: 'intel',       Icon: Lightbulb,     label: 'Industry intel' },
          ] as const).map(({ type, Icon, label }) => (
            <button key={type} type="button" onClick={() => setNoteType(type)}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                noteType === type
                  ? 'bg-indigo-500/20 text-indigo-300 ring-1 ring-indigo-500/40'
                  : 'text-slate-500 hover:text-slate-300 ring-1 ring-white/5'
              }`}>
              <Icon size={11} /> {label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3">
          <textarea
            value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder={
              noteType === 'performance'
                ? 'e.g. Sold out Thuishaven last Saturday. Crowd response excellent, support act exceeded expectations.'
                : noteType === 'correction'
                ? 'e.g. Momentum score seems too high — comparable artists listed don\'t match the sound at all.'
                : 'e.g. Switching from Hector to UTA next month. Big collab release dropping in Q3.'
            }
            rows={3}
            className="w-full resize-none rounded-lg bg-[#1e2535] p-3 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
          <div className="flex justify-end">
            <button type="button" onClick={handleAdd} disabled={!draft.trim()}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-40">
              Log Observation
            </button>
          </div>
        </div>

        {notes.length > 0 && (
          <div className="mt-4 flex flex-col gap-2 border-t border-white/5 pt-4">
            {notes.map(n => {
              const typeMap: Record<string, { badge: string; cls: string }> = {
                performance: { badge: 'Live feedback', cls: 'bg-emerald-500/10 text-emerald-400' },
                correction:  { badge: 'Correction',    cls: 'bg-amber-500/10 text-amber-400' },
                intel:       { badge: 'Intel',          cls: 'bg-indigo-500/10 text-indigo-400' },
              }
              const { badge, cls } = typeMap[n.noteType ?? 'performance'] ?? typeMap.performance
              return (
                <div key={n.id} className="rounded-lg bg-[#1e2535] p-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm text-slate-200">{n.text}</p>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${cls}`}>{badge}</span>
                  </div>
                  <span className="mt-1 block text-xs text-slate-500">
                    {new Date(n.createdAt).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* 3. NL / AMSTERDAM SECTION */}
      {(pfFans != null || pfTotalPerformances != null || nlEvents.length > 0) && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <Globe size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">NL / Amsterdam Presence</h2>
          </div>

          {/* Partyflock KPIs */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Partyflock Fans", value: fmt(pfFans) },
              { label: "NL Performances", value: pfTotalPerformances ?? "—" },
              { label: "Upcoming NL", value: pfUpcomingPerformances ?? "—" },
              { label: "NL Genres", value: (pfGenres ?? []).slice(0, 2).join(", ") || "—" },
            ].map(kpi => (
              <div key={kpi.label} className="rounded-lg bg-[#1e2535] p-3">
                <p className="text-xs text-slate-500">{kpi.label}</p>
                <p className="mt-1 text-lg font-semibold text-slate-100">{kpi.value}</p>
              </div>
            ))}
          </div>

          {/* NL Events table */}
          {nlEvents.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Recent NL/Amsterdam Events</p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500">
                    <th className="pb-1 pr-4 font-medium">Date</th>
                    <th className="pb-1 pr-4 font-medium">Venue</th>
                    <th className="pb-1 font-medium">City</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {nlEvents.slice(0, 8).map((e, i) => (
                    <tr key={i}>
                      <td className="py-1.5 pr-4 text-slate-400">{e.date?.slice(0, 10)}</td>
                      <td className="py-1.5 pr-4 text-slate-200">{e.venue}</td>
                      <td className="py-1.5 text-slate-400">{e.city}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* GROWTH SIGNALS */}
      {mlFeatures && Object.values(mlFeatures).some(v => v != null) && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <TrendingUp size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Growth Signals</h2>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[
              { label: 'SP Listeners 30d', key: 'sp_listeners_30d_pct', isPct: true },
              { label: 'SP Listeners 90d', key: 'sp_listeners_90d_pct', isPct: true },
              { label: 'Acceleration ↑↓', key: 'sp_listeners_accel', isPct: true },
              { label: 'Cross-Platform 30d', key: 'cross_platform_momentum_30d', isPct: true },
              { label: 'Platforms Growing', key: 'platforms_growing_30d', isPct: false },
            ].map(({ label, key, isPct }) => {
              const v = mlFeatures[key]
              return (
                <div key={key} className="rounded-lg bg-[#1e2535] p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
                  {v != null ? (
                    <p className={`mt-1 text-lg font-bold ${!isPct ? 'text-slate-100' : v > 0 ? 'text-emerald-400' : v < 0 ? 'text-rose-400' : 'text-slate-400'}`}>
                      {isPct ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : Math.round(v)}
                    </p>
                  ) : (
                    <p className="mt-1 text-lg font-bold text-slate-500">—</p>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 4. MULTI-PLATFORM GROWTH CHART */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Growth — 12 months</h2>
          </div>
          {multiTimeseries.length > 1 && (
            <div className="flex gap-1">
              {multiTimeseries.map(m => (
                <button key={m.platform} type="button" onClick={() => setActivePlatform(m.platform)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    activePlatform === m.platform ? "bg-indigo-500/20 text-indigo-300" : "text-slate-400 hover:text-slate-200"
                  }`}>
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
                <Tooltip contentStyle={{ background: "#1e2535", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, color: "#f1f5f9" }}
                  labelStyle={{ color: "#94a3b8" }}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(v: any) => [fmt(v), activeTs?.label ?? 'Spotify Listeners']} />
                <Line type="monotone" dataKey="value" stroke={PLATFORM_COLORS[activePlatform] ?? "#6366f1"} strokeWidth={2} dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      {/* 5. TRACKS & PLAYLISTS */}
      {(tracks.length > 0 || (playlists && playlists.length > 0)) && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <Music2 size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Tracks & Playlists</h2>
          </div>
          <TracksTabs tracks={tracks} playlists={playlists ?? []} />
        </section>
      )}

      {/* 6. ALBUMS */}
      {albums.length > 0 && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <Disc3 size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Releases</h2>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {albums.slice(0, 10).map((a, i) => (
              <div key={i} className="flex flex-col gap-1.5 rounded-xl bg-[#1e2535] p-3">
                <div className="aspect-square w-full overflow-hidden rounded-lg bg-[#161b27]">
                  {a.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={a.image_url} alt={a.name} className="h-full w-full object-cover" crossOrigin="anonymous" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center">
                      <Disc3 size={24} className="text-[#64748b]" />
                    </div>
                  )}
                </div>
                <p className="text-xs font-medium text-slate-200 line-clamp-2 leading-snug">{a.name}</p>
                <div className="flex items-center justify-between">
                  {a.release_date && (
                    <span className="text-[10px] text-slate-500">{String(a.release_date).slice(0, 7)}</span>
                  )}
                  {a.type && (
                    <span className="rounded-full bg-white/5 px-1.5 py-0.5 text-[10px] capitalize text-slate-400">{a.type}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 7. MILESTONES */}
      {(validationEvents.length > 0 || cmMilestones.length > 0) && (
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
                  : <Circle size={15} className="mt-0.5 shrink-0 text-slate-500" />}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-200">
                    {EVENT_TYPE_LABELS[ve.event_type] ?? ve.event_type.replace(/_/g, " ")}
                  </p>
                  {ve.source && <p className="text-xs text-slate-500">{ve.source}</p>}
                </div>
                <span className="shrink-0 text-xs text-slate-500">{ve.event_date ? String(ve.event_date).slice(0, 10) : ""}</span>
                {!ve.confirmed && (
                  <span className="shrink-0 rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-400">unconfirmed</span>
                )}
              </div>
            ))}
            {cmMilestones.map((m, i) => {
              const source = milestoneSource(m)
              const url = String(m.url ?? m.event_url ?? m.source_url ?? "")
              const date = milestoneDate(m)
              const detail = String(m.description ?? m.detail ?? m.context ?? m.value ?? "")
              return (
                <div key={`cm-${i}`} className="flex items-start gap-3 rounded-lg bg-[#1e2535] px-4 py-3">
                  <Sparkles size={15} className="mt-0.5 shrink-0 text-indigo-400" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium capitalize text-slate-200">{milestoneText(m)}</p>
                    {detail && <p className="mt-0.5 text-xs leading-relaxed text-slate-400">{detail}</p>}
                    <p className="mt-1 text-xs text-slate-500">
                      Achieved via {url ? (
                        <a href={url} target="_blank" rel="noopener noreferrer" className="text-indigo-300 hover:text-indigo-200">
                          {source}
                        </a>
                      ) : source}
                    </p>
                  </div>
                  {date && <span className="shrink-0 text-xs text-slate-500">{date}</span>}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 7. FAN CITIES */}
      {topCities.length > 0 && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <MapPin size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Fan Cities</h2>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topCities} layout="vertical" margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
                <XAxis type="number" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false}
                  tickFormatter={v => v > 0 && v < 1 ? `${(v * 100).toFixed(0)}%` : String(v)} />
                <YAxis type="category" dataKey="city" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} width={80} />
                <Tooltip contentStyle={{ background: "#1e2535", border: "none", borderRadius: 8, color: "#f1f5f9" }}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(v: any) => [v < 1 ? `${(v * 100).toFixed(1)}%` : v]} />
                <Bar dataKey={topCities[0]?.pct != null ? "pct" : "count"} radius={[0, 4, 4, 0]}>
                  {topCities.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? "#6366f1" : "#1e2535"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {/* 8. SIMILAR ARTISTS */}
      {similarArtists.length > 0 && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <Users size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Similar Artists</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {similarArtists.map(name => (
              <span key={name} className="rounded-full bg-[#1e2535] px-3 py-1.5 text-sm text-slate-300 ring-1 ring-white/5">
                {name}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* 9. INSTAGRAM AUDIENCE */}
      {igTopCountries.length > 0 && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <Globe size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Instagram Audience — Top Countries</h2>
          </div>
          <div className="flex flex-col gap-2">
            {igTopCountries.map(c => {
              const pct = Number(c.percent)
              return (
                <div key={c.code} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 text-xs text-slate-400">{c.name}</span>
                  <div className="flex-1 overflow-hidden rounded-full bg-white/5 h-2">
                    <div
                      className="h-full rounded-full bg-[#E1306C]/60"
                      style={{ width: `${Math.min(100, pct)}%` }}
                    />
                  </div>
                  <span className="w-12 shrink-0 text-right text-xs font-medium text-slate-300">{pct.toFixed(1)}%</span>
                  <span className="w-16 shrink-0 text-right text-xs text-slate-500">{fmt(c.followers)}</span>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 10. NOTEWORTHY INSIGHTS */}
      {noteworthy.length > 0 && (
        <section className="rounded-xl bg-[#161b27] p-6">
          <div className="mb-4 flex items-center gap-2">
            <Sparkles size={18} className="text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-100">Noteworthy Insights</h2>
          </div>
          <div className="flex flex-col gap-2">
            {noteworthy.slice(0, 5).map((n, i) => (
              <div key={i} className="rounded-lg bg-[#1e2535] px-4 py-3">
                {n.title && <p className="text-sm font-medium text-slate-200">{n.title}</p>}
                {n.description && <p className="mt-0.5 text-xs text-slate-400">{n.description}</p>}
                {n.value && <p className="mt-1 text-sm font-semibold text-indigo-300">{n.value}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 11. SHOW HISTORY */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-6 flex items-center gap-2">
          <Calendar size={18} className="text-indigo-400" />
          <h2 className="text-lg font-semibold text-slate-100">Show History</h2>
        </div>
        <ShowHistoryTabs
          raEvents={sortedEvents}
          pfEvents={pfEvents ?? []}
          beatportChartEntries={beatportChartEntries ?? []}
          traxsourceChartEntries={traxsourceChartEntries ?? []}
        />
      </section>

      {/* Booker Intelligence is shown earlier on the page, above NL/Amsterdam */}
    </div>
  )
}
