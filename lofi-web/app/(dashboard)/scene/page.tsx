'use client'

import { useState } from 'react'
import {
  Sparkles,
  ChevronDown,
  TrendingUp,
  TrendingDown,
  Minus,
  CalendarDays,
  Disc3,
  PartyPopper,
  MapPin,
  AlertTriangle,
  ArrowUpRight,
} from 'lucide-react'

interface TrendTile {
  id: string
  label: string
  value: string
  sub: string
  direction: 'up' | 'down' | 'flat'
  spark: number[]
}

interface LabelRow {
  name: string
  releases: number
  keyArtist: string
  trend: 'up' | 'down' | 'flat'
}

interface VenueRow {
  name: string
  events: number
  topArtist: string
}

interface PatternAlert {
  id: string
  type: 'genre' | 'label' | 'festival'
  description: string
  artists: string[]
}

const TRENDS: TrendTile[] = [
  { id: 't1', label: 'Tech-House Momentum', value: '78', sub: '+6 vs last week', direction: 'up', spark: [40, 44, 42, 50, 58, 62, 71, 78] },
  { id: 't2', label: 'NL Event Activity', value: '142', sub: 'Partyflock events · +18', direction: 'up', spark: [110, 118, 120, 124, 130, 128, 138, 142] },
  { id: 't3', label: 'Label Activity', value: '23', sub: 'new releases this week', direction: 'flat', spark: [20, 24, 19, 22, 25, 21, 24, 23] },
  { id: 't4', label: 'Festival Announcements', value: '9', sub: 'new lineups detected', direction: 'down', spark: [16, 14, 15, 12, 13, 11, 10, 9] },
]

const LABELS: LabelRow[] = [
  { name: 'Drumcode', releases: 6, keyArtist: 'Enrico Sangiuliano', trend: 'up' },
  { name: 'Afterlife', releases: 4, keyArtist: 'Massano', trend: 'up' },
  { name: 'Hot Creations', releases: 3, keyArtist: 'PAWSA', trend: 'flat' },
  { name: 'Solid Grooves', releases: 5, keyArtist: 'Michael Bibi', trend: 'up' },
  { name: 'Defected', releases: 7, keyArtist: 'Dennis Quin', trend: 'down' },
  { name: 'Innervisions', releases: 2, keyArtist: 'Âme', trend: 'flat' },
  { name: 'Knee Deep In Sound', releases: 3, keyArtist: 'Hot Since 82', trend: 'up' },
]

const VENUES: VenueRow[] = [
  { name: 'Shelter', events: 12, topArtist: 'Reinier Zonneveld' },
  { name: 'Thuishaven', events: 9, topArtist: 'Joris Voorn' },
  { name: 'De School', events: 7, topArtist: 'Job Jobse' },
  { name: 'Melkweg', events: 14, topArtist: 'Chris Stussy' },
  { name: 'Paradiso', events: 11, topArtist: 'Colyn' },
]

const COMPETITOR_BOOKINGS = [
  { venue: 'Shelter', artist: 'Reinier Zonneveld', date: '28 Jun', watched: true },
  { venue: 'Thuishaven', artist: 'Joris Voorn', date: '29 Jun', watched: false },
  { venue: 'De Marktkantine', artist: 'Verraco', date: '4 Jul', watched: true },
  { venue: 'Melkweg', artist: 'Chris Stussy', date: '5 Jul', watched: false },
  { venue: 'RADION', artist: 'SPFDJ', date: '11 Jul', watched: true },
  { venue: 'Garage Noord', artist: 'Nicky Soft Touch', date: '12 Jul', watched: false },
  { venue: 'Paradiso', artist: 'Colyn', date: '18 Jul', watched: false },
  { venue: 'Lofi', artist: 'Anetha', date: '19 Jul', watched: true },
  { venue: 'Shelter', artist: 'Hector Oaks', date: '25 Jul', watched: false },
]

const ALERTS: PatternAlert[] = [
  { id: 'a1', type: 'label', description: '3 tech-house artists from Solid Grooves booked at ADE 2025', artists: ['Michael Bibi', 'PAWSA', 'Archie Hamilton'] },
  { id: 'a2', type: 'genre', description: 'Hard techno bookings up 24% across Amsterdam venues this month', artists: ['SPFDJ', 'Hector Oaks', 'Anetha'] },
  { id: 'a3', type: 'festival', description: 'Awakenings dropped 2 names already on your watchlist', artists: ['Verraco', 'Colyn'] },
]

function Sparkline({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const w = 96
  const h = 32
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`)
    .join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible" aria-hidden="true">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function TrendArrow({ direction }: { direction: 'up' | 'down' | 'flat' }) {
  if (direction === 'up') return <TrendingUp className="size-4 text-emerald-400" aria-label="trending up" />
  if (direction === 'down') return <TrendingDown className="size-4 text-rose-400" aria-label="trending down" />
  return <Minus className="size-4 text-[#94a3b8]" aria-label="flat" />
}

export default function ScenePage() {
  const [briefOpen, setBriefOpen] = useState(true)

  return (
    <div className="mx-auto max-w-7xl">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[#f1f5f9]">Scene Intelligence</h1>
          <p className="mt-1 text-sm text-[#94a3b8]">Market trends for electronic music — Amsterdam focus</p>
          <p className="mt-1 text-xs text-[#64748b]">Week of 23 June 2025</p>
        </div>
        <button
          type="button"
          className="inline-flex shrink-0 items-center gap-2 rounded-md bg-[#6366f1] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#5457e5]"
        >
          <Sparkles className="size-4" aria-hidden="true" />
          Generate Weekly Brief
        </button>
      </div>

      {/* AI Weekly Brief */}
      <section className="mt-6 overflow-hidden rounded-xl border-l-4 border-[#6366f1] bg-[#161b27]">
        <button
          type="button"
          onClick={() => setBriefOpen((o) => !o)}
          className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left"
          aria-expanded={briefOpen}
        >
          <span className="flex items-center gap-2">
            <Sparkles className="size-4 text-[#818cf8]" aria-hidden="true" />
            <span className="text-sm font-semibold text-[#f1f5f9]">AI Weekly Brief</span>
            <span className="text-xs text-[#64748b]">generated 2h ago</span>
          </span>
          <ChevronDown
            className={`size-4 text-[#94a3b8] transition-transform ${briefOpen ? 'rotate-180' : ''}`}
            aria-hidden="true"
          />
        </button>
        {briefOpen && (
          <div className="space-y-4 px-5 pb-5 text-sm leading-relaxed text-[#cbd5e1]">
            <p>
              Tech-house momentum continued its climb this week, driven by a wave of Solid Grooves and Drumcode releases
              that are over-indexing in Amsterdam streaming data. Three watchlist artists posted double-digit Spotify
              growth, while festival lineup announcements slowed ahead of the ADE reveal cycle.
            </p>
            <p>
              NL event activity rose 18% week-over-week on Partyflock, with Shelter and Melkweg leading club programming.
              Hard techno bookings are quietly accelerating across the city — a pattern worth tracking for the Saturday
              Thuishaven nights.
            </p>
            <p>
              Label-side, Drumcode and Solid Grooves were the most active, and several of their artists overlap with your
              current pipeline. Data coverage was strong this week apart from a delayed RA scrape.
            </p>
            <div className="rounded-lg bg-[#1e2535] p-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#818cf8]">Key Actions</p>
              <ul className="space-y-2">
                {[
                  'Lock Verraco before the Awakenings announcement drives up fees.',
                  'Review hard-techno cluster (SPFDJ, Hector Oaks) for a Saturday slot.',
                  'Re-check Colyn data — strong momentum, incomplete RA coverage.',
                ].map((action) => (
                  <li key={action} className="flex items-start gap-2 text-[#f1f5f9]">
                    <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-[#6366f1]" aria-hidden="true" />
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </section>

      {/* Trend tiles */}
      <div className="mt-6 flex gap-4 overflow-x-auto pb-2">
        {TRENDS.map((t) => {
          const color = t.direction === 'up' ? '#34d399' : t.direction === 'down' ? '#fb7185' : '#94a3b8'
          const Icon = t.id === 't1' ? TrendingUp : t.id === 't2' ? CalendarDays : t.id === 't3' ? Disc3 : PartyPopper
          return (
            <div key={t.id} className="flex w-64 shrink-0 flex-col rounded-xl border border-[#1e2535] bg-[#161b27] p-4">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-xs font-medium text-[#94a3b8]">
                  <Icon className="size-4 text-[#818cf8]" aria-hidden="true" />
                  {t.label}
                </span>
                <TrendArrow direction={t.direction} />
              </div>
              <div className="mt-3 flex items-end justify-between">
                <div>
                  <p className="text-2xl font-semibold text-[#f1f5f9]">{t.value}</p>
                  <p className="mt-1 text-xs text-[#64748b]">{t.sub}</p>
                </div>
                <Sparkline data={t.spark} color={color} />
              </div>
            </div>
          )
        })}
      </div>

      {/* Two-column: labels + venues */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {/* Rising labels */}
        <section className="rounded-xl border border-[#1e2535] bg-[#161b27]">
          <h2 className="border-b border-[#1e2535] px-5 py-4 text-sm font-semibold text-[#f1f5f9]">
            Active Labels This Month
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-[#64748b]">
                  <th className="px-5 py-2 font-medium">Label</th>
                  <th className="px-5 py-2 font-medium">Releases</th>
                  <th className="px-5 py-2 font-medium">Key Artist</th>
                  <th className="px-5 py-2 font-medium">Trend</th>
                </tr>
              </thead>
              <tbody>
                {LABELS.map((l) => (
                  <tr key={l.name} className="border-t border-[#1e2535]">
                    <td className="px-5 py-3 font-medium text-[#f1f5f9]">{l.name}</td>
                    <td className="px-5 py-3 text-[#94a3b8]">{l.releases}</td>
                    <td className="px-5 py-3 text-[#94a3b8]">{l.keyArtist}</td>
                    <td className="px-5 py-3">
                      <TrendArrow direction={l.trend} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Venue activity */}
        <section className="rounded-xl border border-[#1e2535] bg-[#161b27]">
          <div className="flex items-center gap-2 border-b border-[#1e2535] px-5 py-4">
            <MapPin className="size-4 text-[#818cf8]" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-[#f1f5f9]">Venue Activity — Amsterdam</h2>
          </div>
          <div className="flex h-32 items-center justify-center border-b border-dashed border-[#1e2535] text-xs text-[#64748b]">
            Map view coming soon
          </div>
          <ul className="divide-y divide-[#1e2535]">
            {VENUES.map((v) => (
              <li key={v.name} className="flex items-center justify-between px-5 py-3">
                <div>
                  <p className="text-sm font-medium text-[#f1f5f9]">{v.name}</p>
                  <p className="text-xs text-[#64748b]">Top: {v.topArtist}</p>
                </div>
                <span className="rounded-full bg-[#1e2535] px-3 py-1 text-xs font-medium text-[#94a3b8]">
                  {v.events} events
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* Competitor bookings + alerts */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className="rounded-xl border border-[#1e2535] bg-[#161b27] lg:col-span-2">
          <h2 className="border-b border-[#1e2535] px-5 py-4 text-sm font-semibold text-[#f1f5f9]">
            What Other Amsterdam Venues Are Booking
          </h2>
          <ul className="divide-y divide-[#1e2535]">
            {COMPETITOR_BOOKINGS.map((b, i) => (
              <li key={i} className="flex items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-[#f1f5f9]">{b.artist}</p>
                  <p className="text-xs text-[#64748b]">
                    {b.venue} · {b.date}
                  </p>
                </div>
                {b.watched && (
                  <span className="shrink-0 rounded-full bg-[#6366f1]/15 px-2.5 py-1 text-xs font-medium text-[#818cf8]">
                    Also on your watchlist
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>

        {/* Pattern alerts */}
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-[#f1f5f9]">AI Pattern Alerts</h2>
          {ALERTS.map((a) => (
            <div key={a.id} className="rounded-xl border border-[#1e2535] bg-[#161b27] p-4">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-400" aria-hidden="true" />
                <p className="text-sm text-[#f1f5f9]">{a.description}</p>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {a.artists.map((artist) => (
                  <span key={artist} className="rounded-full bg-[#1e2535] px-2.5 py-1 text-xs text-[#94a3b8]">
                    {artist}
                  </span>
                ))}
              </div>
              <button
                type="button"
                className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-[#818cf8] hover:text-[#a5b4fc]"
              >
                Explore <ArrowUpRight className="size-3.5" aria-hidden="true" />
              </button>
            </div>
          ))}
        </section>
      </div>
    </div>
  )
}
