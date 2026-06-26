"use client"

import { useState } from "react"
import {
  ArrowLeft, Star, TrendingUp, Calendar, Sparkles,
  Music2, Users, CheckCircle2, Circle, MapPin, Building2,
  ExternalLink, Globe, Disc3,
} from "lucide-react"
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar, Cell,
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
  notes: Array<{ id: string; text: string; createdAt: string }>
  onAddNote: (text: string) => void
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

function SignalBar({ label, weight, value }: { label: string; weight: number; value: number }) {
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
      <span className="text-2xl font-bold text-slate-100">{Math.round(value)}</span>
    </div>
  )
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

export default function ArtistProfile({
  artist, bookingSignals, growthData, multiTimeseries, events, notes,
  onAddNote, isFavorite, onFavoriteToggle, onBack,
  tracks, validationEvents, similarArtists,
  socialLinks = [], fanCities = [], noteworthy = [],
  pfFans, pfTotalPerformances, pfUpcomingPerformances, pfGenres,
  instagramAudience, xgboostGrowth90d,
}: ArtistProfileProps) {
  const [draft, setDraft] = useState("")
  const [activePlatform, setActivePlatform] = useState<string>(multiTimeseries[0]?.platform ?? "spotify")
  const verdict = getVerdict(bookingSignals.composite)
  const firstLetter = artist.name.trim().charAt(0).toUpperCase() || "?"
  const statusClass = STATUS_STYLES[artist.status] ?? STATUS_STYLES.pending
  const sortedEvents = [...events].sort((a, b) => +new Date(a.date) - +new Date(b.date))
  const nlEvents = events.filter(e => e.country === 'NL' || e.country === 'Netherlands' || e.city?.toLowerCase().includes('amsterdam'))

  const activeTs = multiTimeseries.find(m => m.platform === activePlatform)
  const rawChartData = activeTs
    ? activeTs.data.map(p => ({ date: p.date.slice(0, 7), value: p.value }))
    : growthData.map(p => ({ date: p.date.slice(0, 7), value: p.listeners }))

  // Build projected forecast points if Spotify + xgboost prediction available
  const isSpotify = !activeTs || activePlatform === 'spotify'
  const forecastPoints: { date: string; value?: number; projected?: number }[] = []
  if (isSpotify && xgboostGrowth90d != null && rawChartData.length > 0) {
    const lastPoint = rawChartData[rawChartData.length - 1]
    const lastVal = lastPoint.value
    const growthPer30d = xgboostGrowth90d / 3
    for (let m = 1; m <= 3; m++) {
      const [yr, mo] = lastPoint.date.split('-').map(Number)
      const d = new Date(yr, mo - 1 + m, 1)
      const label = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      forecastPoints.push({ date: label, projected: Math.round(lastVal * (1 + growthPer30d * m)) })
    }
  }

  const chartData: { date: string; value?: number; projected?: number }[] =
    forecastPoints.length > 0
      ? [
          ...rawChartData.map((p, i) =>
            i === rawChartData.length - 1
              ? { ...p, projected: p.value } // bridge last historical point to forecast
              : p
          ),
          ...forecastPoints,
        ]
      : rawChartData

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
    onAddNote(text)
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
              <div className="flex flex-col items-center">
                <span className="text-3xl font-bold text-slate-100">{Math.round(bookingSignals.composite)}</span>
                <span className="text-[10px] uppercase tracking-wide text-slate-500">Composite</span>
              </div>
            </ScoreRing>
            <span className={`rounded-full px-3 py-1 text-sm font-semibold ${verdict.className}`}>{verdict.label}</span>
          </div>
        </div>

        {/* Bio */}
        {artist.description && (
          <p className="mt-4 border-t border-white/5 pt-4 text-sm leading-relaxed text-slate-400 line-clamp-3">
            {artist.description}
          </p>
        )}
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
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${verdict.className}`}>{verdict.label}</span>
          </div>
        </div>
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
                  formatter={(v: number, name: string) => [fmt(v), name === 'projected' ? '90d Forecast' : 'Listeners']} />
                <Line type="monotone" dataKey="value" stroke={PLATFORM_COLORS[activePlatform] ?? "#6366f1"} strokeWidth={2} dot={false} connectNulls={false} />
                {forecastPoints.length > 0 && (
                  <Line type="monotone" dataKey="projected" stroke="#818cf8" strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls />
                )}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      {/* 5. TRACKS */}
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
        </section>
      )}

      {/* 6. MILESTONES */}
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
                  formatter={(v: number) => [v < 1 ? `${(v * 100).toFixed(1)}%` : v]} />
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

      {/* 11. EVENT TIMELINE */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-6 flex items-center gap-2">
          <Calendar size={18} className="text-indigo-400" />
          <h2 className="text-lg font-semibold text-slate-100">Event Timeline ({sortedEvents.length} events)</h2>
        </div>
        {sortedEvents.length === 0 ? (
          <p className="text-sm text-slate-500">No events recorded.</p>
        ) : (
          <div className="relative overflow-x-auto pb-2">
            <div className="relative flex min-w-max items-start gap-12 px-2">
              <div className="absolute left-0 right-0 top-2 h-px bg-white/10" />
              {sortedEvents.map((e, i) => (
                <div key={`${e.venue}-${i}`} className="group relative flex flex-col items-center gap-2">
                  <span className={`relative z-10 h-4 w-4 rounded-full ring-4 ring-[#161b27] ${e.festival ? "bg-indigo-400" : "bg-slate-500"}`} />
                  <span className="text-xs font-medium text-slate-300">{e.venue}</span>
                  <span className="text-[11px] text-slate-500">
                    {new Date(e.date).toLocaleDateString("en-US", { month: "short", year: "numeric" })}
                  </span>
                  <div className="pointer-events-none absolute -top-10 left-1/2 z-20 -translate-x-1/2 whitespace-nowrap rounded-md bg-[#1e2535] px-2 py-1 text-xs text-slate-200 opacity-0 shadow-lg ring-1 ring-white/10 transition-opacity group-hover:opacity-100">
                    {e.city && `${e.city} · `}{e.attending.toLocaleString()} cap{e.festival ? " · Festival" : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* 12. NOTES PANEL */}
      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-4 flex items-center gap-2">
          <Sparkles size={18} className="text-indigo-400" />
          <h2 className="text-lg font-semibold text-slate-100">Notes</h2>
        </div>
        <div className="flex flex-col gap-3">
          <textarea value={draft} onChange={e => setDraft(e.target.value)}
            placeholder="Add a note about this artist…" rows={3}
            className="w-full resize-none rounded-lg bg-[#1e2535] p-3 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50" />
          <div className="flex justify-end">
            <button type="button" onClick={handleAdd} disabled={!draft.trim()}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-40">
              Add Note
            </button>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3">
          {notes.length === 0 ? (
            <p className="text-sm text-slate-500">No notes yet.</p>
          ) : (
            notes.map(n => (
              <div key={n.id} className="rounded-lg bg-[#1e2535] p-3">
                <p className="text-sm text-slate-200">{n.text}</p>
                <span className="mt-1 block text-xs text-slate-500">
                  {new Date(n.createdAt).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                </span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  )
}
