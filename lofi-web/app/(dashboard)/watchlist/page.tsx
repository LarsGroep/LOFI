"use client"

import { useMemo, useState } from "react"
import {
  Star,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  MoreHorizontal,
  TrendingUp,
  TrendingDown,
  GitCompare,
} from "lucide-react"

interface WatchlistArtist {
  id: string
  name: string
  imageUrl: string | null
  genre: string
  status: string
  composite: number | null
  momentum: number | null
  growth: number | null
  spotifyDelta30d: number | null
  raEvents: number | null
  updatedAt: string
}

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-slate-700 text-slate-300",
  candidate: "bg-indigo-500/20 text-indigo-400",
  accepted: "bg-cyan-500/20 text-cyan-400",
  booked: "bg-green-500/20 text-green-400",
}

const STATUS_OPTIONS = ["pending", "candidate", "accepted", "booked"]

// ---- Mock data (TODO: replace with SWR fetch from Supabase artist_watchlists) ----
const MOCK: WatchlistArtist[] = [
  { id: "enrico", name: "Enrico Sangiuliano", imageUrl: null, genre: "Techno", status: "booked", composite: 88, momentum: 84, growth: 80, spotifyDelta30d: 18, raEvents: 14, updatedAt: "2025-06-26T08:00:00Z" },
  { id: "verraco", name: "Verraco", imageUrl: null, genre: "Tech-House", status: "candidate", composite: 84, momentum: 90, growth: 76, spotifyDelta30d: 24, raEvents: 9, updatedAt: "2025-06-26T06:00:00Z" },
  { id: "sansibar", name: "Sansibar", imageUrl: null, genre: "Afro House", status: "candidate", composite: 78, momentum: 78, growth: 72, spotifyDelta30d: 12, raEvents: 7, updatedAt: "2025-06-25T18:00:00Z" },
  { id: "kettama", name: "KETTAMA", imageUrl: null, genre: "House", status: "accepted", composite: 71, momentum: 71, growth: 68, spotifyDelta30d: -4, raEvents: 11, updatedAt: "2025-06-24T12:00:00Z" },
  { id: "azu", name: "Azu Tiwaline", imageUrl: null, genre: "Techno", status: "pending", composite: 61, momentum: 61, growth: 55, spotifyDelta30d: 7, raEvents: 5, updatedAt: "2025-06-22T09:00:00Z" },
  { id: "dexphase", name: "DexPhase", imageUrl: null, genre: "Tech-House", status: "pending", composite: 42, momentum: 58, growth: 38, spotifyDelta30d: -2, raEvents: 2, updatedAt: "2025-06-20T15:00:00Z" },
]

type SortKey = "name" | "status" | "composite" | "momentum" | "growth" | "spotifyDelta30d" | "raEvents" | "updatedAt"
type GroupBy = "none" | "status" | "genre"

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.round(diff / 3_600_000)
  if (h < 1) return "just now"
  if (h < 24) return `${h}h ago`
  const d = Math.round(h / 24)
  return `${d}d ago`
}

function scoreDot(value: number | null): string {
  if (value === null) return "bg-slate-600"
  if (value >= 65) return "bg-green-400"
  if (value >= 45) return "bg-amber-400"
  return "bg-red-400"
}

export default function WatchlistPage() {
  const [artists, setArtists] = useState<WatchlistArtist[]>(MOCK)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [sortKey, setSortKey] = useState<SortKey>("composite")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [groupBy, setGroupBy] = useState<GroupBy>("none")
  const [menuOpen, setMenuOpen] = useState<string | null>(null)

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir("desc")
    }
  }

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function handleRemove(id: string) {
    setArtists((prev) => prev.filter((a) => a.id !== id))
    setSelected((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
    setMenuOpen(null)
  }

  function handleStatusChange(id: string, status: string) {
    setArtists((prev) => prev.map((a) => (a.id === id ? { ...a, status } : a)))
    setMenuOpen(null)
  }

  const sorted = useMemo(() => {
    const copy = [...artists]
    copy.sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (av === null) return 1
      if (bv === null) return -1
      let cmp: number
      if (typeof av === "string" && typeof bv === "string") {
        cmp = sortKey === "updatedAt" ? +new Date(av) - +new Date(bv) : av.localeCompare(bv)
      } else {
        cmp = (av as number) - (bv as number)
      }
      return sortDir === "asc" ? cmp : -cmp
    })
    return copy
  }, [artists, sortKey, sortDir])

  const groups = useMemo(() => {
    if (groupBy === "none") return [{ label: null as string | null, rows: sorted }]
    const map = new Map<string, WatchlistArtist[]>()
    for (const a of sorted) {
      const key = groupBy === "status" ? a.status : a.genre
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(a)
    }
    return Array.from(map.entries()).map(([label, rows]) => ({ label, rows }))
  }, [sorted, groupBy])

  const canCompare = selected.size >= 2

  return (
    <div className="flex flex-col gap-6">
      {/* HEADER */}
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-2xl font-bold text-[#f1f5f9]">Watchlist</h1>
            <p className="text-sm text-[#94a3b8]">Your monitored artists</p>
          </div>
          <span className="rounded-full bg-[#1e2535] px-2.5 py-1 text-xs font-medium text-[#94a3b8]">
            {artists.length} artists
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Group by toggle */}
          <div className="flex items-center gap-1 rounded-lg bg-[#1e2535] p-1">
            {(["none", "status", "genre"] as GroupBy[]).map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setGroupBy(g)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
                  groupBy === g ? "bg-[#6366f1] text-white" : "text-[#94a3b8] hover:text-[#f1f5f9]"
                }`}
              >
                {g === "none" ? "No group" : g}
              </button>
            ))}
          </div>
          <button
            type="button"
            disabled={!canCompare}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              canCompare
                ? "bg-[#6366f1] text-white hover:bg-[#818cf8]"
                : "cursor-not-allowed bg-[#1e2535] text-[#64748b]"
            }`}
          >
            <GitCompare size={16} aria-hidden="true" />
            Compare Selected{selected.size > 0 ? ` (${selected.size})` : ""}
          </button>
        </div>
      </header>

      {/* TABLE or EMPTY STATE */}
      {artists.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-white/10 bg-[#161b27] p-16 text-center">
          <Star size={32} className="text-[#64748b]" />
          <p className="text-base font-medium text-[#f1f5f9]">No artists in your watchlist</p>
          <a href="/dashboard" className="text-sm font-medium text-[#6366f1] hover:text-[#818cf8]">
            Browse artists to add some
          </a>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-white/5 bg-[#161b27]">
          <table className="w-full min-w-[1000px] text-sm">
            <thead>
              <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wide text-[#64748b]">
                <th className="w-10 px-4 py-3" />
                <SortHeader label="Artist" col="name" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <SortHeader label="Status" col="status" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <SortHeader label="Composite" col="composite" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} align="center" />
                <SortHeader label="Momentum" col="momentum" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} align="center" />
                <SortHeader label="Growth" col="growth" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} align="center" />
                <SortHeader label="Spotify 30d" col="spotifyDelta30d" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} align="center" />
                <SortHeader label="RA Events" col="raEvents" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} align="center" />
                <SortHeader label="Updated" col="updatedAt" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <th className="w-12 px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <GroupRows
                  key={group.label ?? "all"}
                  label={group.label}
                  rows={group.rows}
                  selected={selected}
                  menuOpen={menuOpen}
                  onToggleSelect={toggleSelect}
                  onMenuToggle={(id) => setMenuOpen((m) => (m === id ? null : id))}
                  onRemove={handleRemove}
                  onStatusChange={handleStatusChange}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SortHeader({
  label,
  col,
  sortKey,
  sortDir,
  onSort,
  align = "left",
}: {
  label: string
  col: SortKey
  sortKey: SortKey
  sortDir: "asc" | "desc"
  onSort: (k: SortKey) => void
  align?: "left" | "center"
}) {
  const active = sortKey === col
  return (
    <th className={`px-4 py-3 font-medium ${align === "center" ? "text-center" : "text-left"}`}>
      <button
        type="button"
        onClick={() => onSort(col)}
        className={`inline-flex items-center gap-1 transition-colors hover:text-[#f1f5f9] ${
          active ? "text-[#f1f5f9]" : ""
        } ${align === "center" ? "mx-auto" : ""}`}
      >
        {label}
        {active ? (
          sortDir === "asc" ? (
            <ArrowUp size={12} />
          ) : (
            <ArrowDown size={12} />
          )
        ) : (
          <ArrowUpDown size={12} className="opacity-40" />
        )}
      </button>
    </th>
  )
}

function GroupRows({
  label,
  rows,
  selected,
  menuOpen,
  onToggleSelect,
  onMenuToggle,
  onRemove,
  onStatusChange,
}: {
  label: string | null
  rows: WatchlistArtist[]
  selected: Set<string>
  menuOpen: string | null
  onToggleSelect: (id: string) => void
  onMenuToggle: (id: string) => void
  onRemove: (id: string) => void
  onStatusChange: (id: string, status: string) => void
}) {
  return (
    <>
      {label && (
        <tr>
          <td colSpan={10} className="bg-[#1e2535]/50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[#94a3b8]">
            {label} · {rows.length}
          </td>
        </tr>
      )}
      {rows.map((a) => {
        const firstLetter = a.name.trim().charAt(0).toUpperCase() || "?"
        const isSel = selected.has(a.id)
        return (
          <tr
            key={a.id}
            className={`border-b border-white/5 transition-colors hover:bg-[#1e2535] ${isSel ? "bg-[#1e2535]/60" : ""}`}
          >
            <td className="px-4 py-3">
              <input
                type="checkbox"
                checked={isSel}
                onChange={() => onToggleSelect(a.id)}
                aria-label={`Select ${a.name}`}
                className="size-4 cursor-pointer accent-[#6366f1]"
              />
            </td>
            <td className="px-4 py-3">
              <a href={`/artist/${a.id}`} className="flex items-center gap-3 group">
                <div className="size-8 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10">
                  {a.imageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={a.imageUrl || "/placeholder.svg"} alt={a.name} crossOrigin="anonymous" className="size-full object-cover" />
                  ) : (
                    <div className="flex size-full items-center justify-center bg-gradient-to-br from-indigo-600 to-slate-800 text-xs font-bold text-white/90">
                      {firstLetter}
                    </div>
                  )}
                </div>
                <div className="min-w-0">
                  <p className="truncate font-medium text-[#f1f5f9] group-hover:text-[#818cf8]">{a.name}</p>
                  <span className="text-xs text-[#94a3b8]">{a.genre}</span>
                </div>
              </a>
            </td>
            <td className="px-4 py-3">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[a.status] ?? STATUS_STYLES.pending}`}>
                {a.status}
              </span>
            </td>
            <td className="px-4 py-3 text-center">
              <span className="inline-flex items-center gap-1.5 font-medium text-[#f1f5f9]">
                <span className={`size-2 rounded-full ${scoreDot(a.composite)}`} />
                {a.composite ?? "—"}
              </span>
            </td>
            <td className="px-4 py-3 text-center">
              <span className="inline-flex items-center gap-1 text-[#f1f5f9]">
                {a.momentum ?? "—"}
                {a.momentum !== null && (a.momentum >= 60 ? <TrendingUp size={13} className="text-green-400" /> : <TrendingDown size={13} className="text-red-400" />)}
              </span>
            </td>
            <td className="px-4 py-3 text-center text-[#f1f5f9]">{a.growth ?? "—"}</td>
            <td className="px-4 py-3 text-center">
              {a.spotifyDelta30d === null ? (
                <span className="text-[#64748b]">—</span>
              ) : (
                <span className={a.spotifyDelta30d >= 0 ? "text-green-400" : "text-red-400"}>
                  {a.spotifyDelta30d >= 0 ? "+" : ""}
                  {a.spotifyDelta30d}%
                </span>
              )}
            </td>
            <td className="px-4 py-3 text-center text-[#f1f5f9]">{a.raEvents ?? "—"}</td>
            <td className="px-4 py-3 text-[#94a3b8]">{relativeTime(a.updatedAt)}</td>
            <td className="relative px-4 py-3 text-right">
              <button
                type="button"
                onClick={() => onMenuToggle(a.id)}
                aria-label={`Actions for ${a.name}`}
                className="inline-flex size-7 items-center justify-center rounded-md text-[#94a3b8] hover:bg-[#252d3f] hover:text-[#f1f5f9]"
              >
                <MoreHorizontal size={16} />
              </button>
              {menuOpen === a.id && (
                <div className="absolute right-4 top-12 z-20 w-48 overflow-hidden rounded-lg border border-white/10 bg-[#1e2535] py-1 shadow-xl">
                  <a href={`/artist/${a.id}`} className="block px-3 py-2 text-left text-sm text-[#f1f5f9] hover:bg-[#252d3f]">
                    View Profile
                  </a>
                  <div className="border-t border-white/5 px-3 py-1.5 text-xs uppercase tracking-wide text-[#64748b]">
                    Change Status
                  </div>
                  {STATUS_OPTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => onStatusChange(a.id, s)}
                      className="block w-full px-3 py-1.5 text-left text-sm capitalize text-[#94a3b8] hover:bg-[#252d3f] hover:text-[#f1f5f9]"
                    >
                      {s}
                    </button>
                  ))}
                  <button
                    type="button"
                    className="block w-full border-t border-white/5 px-3 py-2 text-left text-sm text-[#94a3b8] hover:bg-[#252d3f] hover:text-[#f1f5f9]"
                  >
                    Add Note
                  </button>
                  <button
                    type="button"
                    onClick={() => onRemove(a.id)}
                    className="block w-full px-3 py-2 text-left text-sm text-red-400 hover:bg-red-500/10"
                  >
                    Remove from Watchlist
                  </button>
                </div>
              )}
            </td>
          </tr>
        )
      })}
    </>
  )
}
