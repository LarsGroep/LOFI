"use client"

import { useMemo, useState, useCallback } from "react"
import useSWR from "swr"
import { Plus, Search, ChevronDown } from "lucide-react"
import type { ArtistListItem, ArtistStatus } from "@/types/supabase"

const fetcher = (url: string) => fetch(url).then(r => r.json())

const COLUMNS: { id: ArtistStatus; label: string; color: string }[] = [
  { id: "pending", label: "Pending", color: "#64748b" },
  { id: "candidate", label: "Candidate", color: "#6366f1" },
  { id: "accepted", label: "Accepted", color: "#22d3ee" },
  { id: "booked", label: "Booked", color: "#4ade80" },
  { id: "rejected", label: "Rejected", color: "#ef4444" },
]

function lofiBadge(score: number | null): string {
  if (score === null) return "bg-slate-700 text-slate-300"
  if (score >= 65) return "bg-green-500/20 text-green-400"
  if (score >= 45) return "bg-amber-500/20 text-amber-400"
  return "bg-red-500/20 text-red-400"
}

function PipelineCard({
  artist,
  onStatusChange,
}: {
  artist: ArtistListItem
  onStatusChange: (id: string, status: ArtistStatus) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const firstLetter = artist.name.trim().charAt(0).toUpperCase() || "?"
  const genre = artist.genres?.[0] ?? "—"
  const snippet = artist.verdictReason
    ? artist.verdictReason.slice(0, 80) + (artist.verdictReason.length > 80 ? "…" : "")
    : null

  return (
    <div className="group flex gap-2 rounded-lg border border-white/5 bg-[#1e2535] p-3 transition-colors hover:border-[#6366f1]/40">
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className="size-10 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10">
              {artist.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={artist.imageUrl} alt={artist.name} crossOrigin="anonymous" className="size-full object-cover" />
              ) : (
                <div className="flex size-full items-center justify-center bg-gradient-to-br from-indigo-600 to-slate-800 text-sm font-bold text-white/90">
                  {firstLetter}
                </div>
              )}
            </div>
            <div className="min-w-0">
              <a href={`/artist/${artist.id}`} className="truncate text-sm font-semibold text-[#f1f5f9] hover:text-[#818cf8] block">
                {artist.name}
              </a>
              <span className="inline-block rounded-full bg-white/5 px-1.5 py-0.5 text-[10px] text-[#94a3b8]">
                {genre}
              </span>
            </div>
          </div>
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-bold ${lofiBadge(artist.lofiFitScore)}`}>
            {artist.lofiFitScore != null ? Math.round(artist.lofiFitScore) : "—"}
          </span>
        </div>

        {artist.verdict && (
          <p className="mt-2 truncate text-xs font-medium text-[#818cf8]">{artist.verdict}</p>
        )}

        {snippet && (
          <p className="mt-1.5 text-xs italic text-[#94a3b8] leading-snug line-clamp-2">{snippet}</p>
        )}

        <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2">
          <div className="flex items-center gap-2 text-[10px] text-[#64748b]">
            {artist.spMonthlyListeners != null && (
              <span>{(artist.spMonthlyListeners / 1000).toFixed(0)}K listeners</span>
            )}
            {artist.raEventCount != null && (
              <span>{artist.raEventCount} RA events</span>
            )}
          </div>
          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen(v => !v)}
              className="text-[10px] text-[#64748b] hover:text-[#94a3b8] rounded px-1.5 py-0.5 hover:bg-[#252d3f]"
            >
              Move ▾
            </button>
            {menuOpen && (
              <div className="absolute right-0 bottom-6 z-20 w-36 overflow-hidden rounded-lg border border-white/10 bg-[#1e2535] py-1 shadow-xl">
                {COLUMNS.filter(c => c.id !== artist.status).map(col => (
                  <button
                    key={col.id}
                    type="button"
                    onClick={() => { onStatusChange(artist.id, col.id); setMenuOpen(false) }}
                    className="block w-full px-3 py-1.5 text-left text-xs text-[#94a3b8] hover:bg-[#252d3f] hover:text-[#f1f5f9] capitalize"
                  >
                    → {col.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function PipelinePage() {
  const { data, error, isLoading, mutate } = useSWR<ArtistListItem[]>('/api/artists?limit=500', fetcher, {
    revalidateOnFocus: false,
  })

  const [query, setQuery] = useState("")

  const handleStatusChange = useCallback(async (id: string, status: ArtistStatus) => {
    // Optimistic update
    mutate(
      (prev) => prev?.map(a => a.id === id ? { ...a, status } : a),
      false
    )
    await fetch(`/api/artists/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_status: status }),
    })
    mutate()
  }, [mutate])

  const artists = useMemo(() => {
    if (!data) return []
    if (!query) return data
    return data.filter(a => a.name.toLowerCase().includes(query.toLowerCase()))
  }, [data, query])

  const grouped = useMemo(() => {
    const map: Record<string, ArtistListItem[]> = {}
    for (const col of COLUMNS) map[col.id] = []
    for (const a of artists) {
      if (map[a.status]) map[a.status].push(a)
    }
    return map
  }, [artists])

  function colAvgLofi(rows: ArtistListItem[]): number | null {
    const vals = rows.map(r => r.lofiFitScore).filter((v): v is number => v != null)
    if (!vals.length) return null
    return Math.round(vals.reduce((s, v) => s + v, 0) / vals.length)
  }

  return (
    <div className="flex h-full flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-[#f1f5f9]">Booking Pipeline</h1>
        <p className="text-sm text-[#94a3b8]">Track every artist through the booking workflow</p>
      </header>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search artists…"
            className="w-full rounded-lg border border-white/5 bg-[#1e2535] py-2 pl-9 pr-3 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:outline-none focus:ring-2 focus:ring-[#6366f1]/50"
          />
        </div>
        {data && (
          <span className="text-xs text-[#64748b]">{data.length} artists total</span>
        )}
      </div>

      {isLoading ? (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {COLUMNS.map(col => (
            <div key={col.id} className="w-[300px] shrink-0 h-64 animate-pulse rounded-xl bg-[#161b27]" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-400">Failed to load pipeline. Check Supabase connection.</p>
      ) : (
        <div className="flex flex-1 gap-4 overflow-x-auto pb-2">
          {COLUMNS.map((col) => {
            const rows = grouped[col.id] ?? []
            const avg = colAvgLofi(rows)
            return (
              <div key={col.id} className="flex w-[300px] shrink-0 flex-col rounded-xl bg-[#161b27]">
                <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="size-2.5 rounded-full" style={{ backgroundColor: col.color }} />
                    <span className="font-semibold" style={{ color: col.color }}>{col.label}</span>
                    <span className="rounded-full bg-[#1e2535] px-2 py-0.5 text-xs font-medium text-[#94a3b8]">
                      {rows.length}
                    </span>
                  </div>
                </div>

                <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-3" style={{ maxHeight: '70vh' }}>
                  {rows.length === 0 ? (
                    <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-white/10 text-xs text-[#64748b]">
                      No artists
                    </div>
                  ) : (
                    rows.map((a) => (
                      <PipelineCard key={a.id} artist={a} onStatusChange={handleStatusChange} />
                    ))
                  )}
                </div>

                <div className="border-t border-white/5 px-4 py-2.5 text-xs text-[#94a3b8]">
                  Avg LOFI fit: <span className="font-semibold text-[#f1f5f9]">{avg ?? "—"}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
