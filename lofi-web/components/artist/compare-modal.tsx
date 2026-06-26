'use client'

import { useState } from 'react'
import { X, Plus, Download, Check } from 'lucide-react'

export interface CompareArtist {
  id: string
  name: string
  imageUrl: string | null
  status: string
  scores: {
    composite: number | null
    momentum: number | null
    growth: number | null
    marketRelevance: number | null
    lofiFit: number | null
  }
  reach: {
    spotifyListeners: number | null
    growth30d: number | null
    raAttending: number | null
    partyflockInterest: number | null
  }
  scene: {
    agency: string | null
    lastFestival: string | null
    nlShows: number | null
    amsterdamShows: number | null
  }
  aiVerdict: string
  aiSummary: string
}

interface CompareModalProps {
  artistIds: string[]
  artists: CompareArtist[]
  onClose: () => void
  onSelect: (artistId: string) => void
}

const VERDICT_STYLES: Record<string, string> = {
  'Book Now': 'bg-emerald-500/15 text-emerald-400',
  Watch: 'bg-[#6366f1]/15 text-[#818cf8]',
  Monitor: 'bg-amber-500/15 text-amber-400',
  Pass: 'bg-rose-500/15 text-rose-400',
}

function Avatar({ artist, size = 40 }: { artist: CompareArtist; size?: number }) {
  if (artist.imageUrl) {
    return (
      <img
        src={artist.imageUrl || '/placeholder.svg'}
        alt={artist.name}
        width={size}
        height={size}
        className="rounded-lg object-cover"
        style={{ width: size, height: size }}
        crossOrigin="anonymous"
      />
    )
  }
  return (
    <div
      className="flex items-center justify-center rounded-lg bg-gradient-to-br from-[#6366f1] to-[#312e81] font-semibold text-white"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {artist.name.charAt(0)}
    </div>
  )
}

function fmt(n: number | null, suffix = ''): string {
  if (n === null) return '—'
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k${suffix}`
  return `${n}${suffix}`
}

export function CompareModal({ artists, onClose, onSelect }: CompareModalProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const cols = artists.slice(0, 3)

  // Determine winners for numeric rows: returns the id with the max value
  function winnerId(getter: (a: CompareArtist) => number | null): string | null {
    let best: { id: string; val: number } | null = null
    let tie = false
    for (const a of cols) {
      const v = getter(a)
      if (v === null) continue
      if (!best || v > best.val) {
        best = { id: a.id, val: v }
        tie = false
      } else if (v === best.val) {
        tie = true
      }
    }
    return tie ? null : best?.id ?? null
  }

  type NumRow = { label: string; get: (a: CompareArtist) => number | null; suffix?: string }

  const scoreRows: NumRow[] = [
    { label: 'Composite Score', get: (a) => a.scores.composite },
    { label: 'Momentum', get: (a) => a.scores.momentum },
    { label: 'Growth', get: (a) => a.scores.growth },
    { label: 'Market Relevance', get: (a) => a.scores.marketRelevance },
    { label: 'LOFI Fit', get: (a) => a.scores.lofiFit },
  ]
  const reachRows: NumRow[] = [
    { label: 'Spotify Monthly Listeners', get: (a) => a.reach.spotifyListeners },
    { label: '30-day Growth %', get: (a) => a.reach.growth30d, suffix: '%' },
    { label: 'RA Attending (total)', get: (a) => a.reach.raAttending },
    { label: 'Partyflock Interest', get: (a) => a.reach.partyflockInterest },
  ]
  const sceneRows: { label: string; get: (a: CompareArtist) => string | number | null }[] = [
    { label: 'Agency', get: (a) => a.scene.agency },
    { label: 'Last Major Festival', get: (a) => a.scene.lastFestival },
    { label: 'NL Shows', get: (a) => a.scene.nlShows },
    { label: 'Amsterdam Shows', get: (a) => a.scene.amsterdamShows },
  ]

  function NumGroup({ title, rows }: { title: string; rows: NumRow[] }) {
    return (
      <>
        <tr>
          <td
            colSpan={cols.length + 1}
            className="bg-[#0e1117] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[#64748b]"
          >
            {title}
          </td>
        </tr>
        {rows.map((row) => {
          const win = winnerId(row.get)
          return (
            <tr key={row.label} className="border-t border-[#1e2535]">
              <td className="px-4 py-3 text-sm text-[#94a3b8]">{row.label}</td>
              {cols.map((a) => {
                const v = row.get(a)
                const isWin = win === a.id && v !== null
                return (
                  <td
                    key={a.id}
                    className={`px-4 py-3 text-center text-sm ${
                      isWin ? 'bg-emerald-500/10 font-semibold text-emerald-400' : 'text-[#f1f5f9]'
                    }`}
                  >
                    {fmt(v, row.suffix)}
                  </td>
                )
              })}
            </tr>
          )
        })}
      </>
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Compare artists"
    >
      <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-white/10 bg-[#161b27] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#1e2535] px-5 py-4">
          <h2 className="text-lg font-semibold text-[#f1f5f9]">Compare Artists</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-[#94a3b8] transition hover:bg-[#1e2535] hover:text-[#f1f5f9]"
            aria-label="Close"
          >
            <X className="size-5" />
          </button>
        </div>

        {/* Table */}
        <div className="overflow-auto">
          <table className="w-full border-collapse">
            <thead className="sticky top-0 z-10">
              <tr className="bg-[#161b27]">
                <th className="w-48 border-b border-[#1e2535] px-4 py-4" />
                {cols.map((a) => (
                  <th key={a.id} className="border-b border-l border-[#1e2535] px-4 py-4 align-top">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <Avatar artist={a} size={56} />
                      <span className="text-sm font-semibold text-[#f1f5f9]">{a.name}</span>
                      <span className="rounded-full bg-[#1e2535] px-2.5 py-0.5 text-xs font-medium text-[#94a3b8]">
                        {a.status}
                      </span>
                      <button
                        type="button"
                        onClick={() => setSelected(a.id)}
                        className={`mt-1 inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                          selected === a.id
                            ? 'bg-[#6366f1] text-white'
                            : 'border border-[#1e2535] text-[#94a3b8] hover:border-[#6366f1] hover:text-[#f1f5f9]'
                        }`}
                      >
                        {selected === a.id ? <Check className="size-3.5" /> : null}
                        {selected === a.id ? 'Selected' : 'Select for booking'}
                      </button>
                    </div>
                  </th>
                ))}
                {cols.length < 3 && (
                  <th className="border-b border-l border-[#1e2535] px-4 py-4">
                    <button
                      type="button"
                      className="flex w-full flex-col items-center gap-2 rounded-lg border border-dashed border-[#1e2535] px-4 py-6 text-xs text-[#64748b] transition hover:border-[#6366f1] hover:text-[#94a3b8]"
                    >
                      <Plus className="size-5" aria-hidden="true" />
                      Add 3rd artist
                    </button>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              <NumGroup title="Scores" rows={scoreRows} />
              <NumGroup title="Reach" rows={reachRows} />

              {/* Scene group (text) */}
              <tr>
                <td
                  colSpan={cols.length + 1}
                  className="bg-[#0e1117] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[#64748b]"
                >
                  Scene
                </td>
              </tr>
              {sceneRows.map((row) => (
                <tr key={row.label} className="border-t border-[#1e2535]">
                  <td className="px-4 py-3 text-sm text-[#94a3b8]">{row.label}</td>
                  {cols.map((a) => {
                    const v = row.get(a)
                    return (
                      <td key={a.id} className="px-4 py-3 text-center text-sm text-[#f1f5f9]">
                        {v === null || v === '' ? <span className="text-[#475569]">—</span> : v}
                      </td>
                    )
                  })}
                </tr>
              ))}

              {/* LOFI Assessment group */}
              <tr>
                <td
                  colSpan={cols.length + 1}
                  className="bg-[#0e1117] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[#64748b]"
                >
                  LOFI Assessment
                </td>
              </tr>
              <tr className="border-t border-[#1e2535]">
                <td className="px-4 py-3 text-sm text-[#94a3b8]">AI Verdict</td>
                {cols.map((a) => (
                  <td key={a.id} className="px-4 py-3 text-center">
                    <span
                      className={`inline-block rounded-full px-2.5 py-1 text-xs font-medium ${
                        VERDICT_STYLES[a.aiVerdict] ?? 'bg-[#1e2535] text-[#94a3b8]'
                      }`}
                    >
                      {a.aiVerdict}
                    </span>
                  </td>
                ))}
              </tr>
              <tr className="border-t border-[#1e2535]">
                <td className="px-4 py-3 align-top text-sm text-[#94a3b8]">AI Summary</td>
                {cols.map((a) => (
                  <td key={a.id} className="px-4 py-3 text-left text-xs leading-relaxed text-[#cbd5e1]">
                    {a.aiSummary}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>

        {/* Bottom bar */}
        <div className="flex flex-col gap-3 border-t border-[#1e2535] px-5 py-4 sm:flex-row sm:items-center">
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-md border border-[#1e2535] px-3 py-2 text-sm text-[#94a3b8] transition hover:border-[#6366f1] hover:text-[#f1f5f9]"
          >
            <Download className="size-4" aria-hidden="true" />
            Export Comparison
          </button>
          <input
            type="text"
            placeholder="Add note about this comparison"
            className="h-9 flex-1 rounded-md border border-[#1e2535] bg-[#0e1117] px-3 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:border-[#6366f1] focus:outline-none focus:ring-1 focus:ring-[#6366f1]"
          />
          <button
            type="button"
            disabled={!selected}
            onClick={() => selected && onSelect(selected)}
            className="inline-flex items-center justify-center rounded-md bg-[#6366f1] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#5457e5] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {selected
              ? `Select ${cols.find((a) => a.id === selected)?.name} for this slot`
              : 'Select an artist for this slot'}
          </button>
        </div>
      </div>
    </div>
  )
}
