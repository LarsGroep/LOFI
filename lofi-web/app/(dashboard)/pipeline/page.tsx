"use client"

import { useMemo, useState } from "react"
import { Plus, GripVertical, Search, ChevronDown } from "lucide-react"

interface PipelineArtist {
  id: string
  name: string
  imageUrl: string | null
  genre: string
  status: string
  composite: number | null
  targetEvent: string | null
  aiMemoSnippet: string | null
  assignedTo: string | null
  lastActivity: string
}

const COLUMNS = [
  { id: "pending", label: "Pending", color: "#64748b" },
  { id: "candidate", label: "Candidate", color: "#6366f1" },
  { id: "accepted", label: "Accepted", color: "#22d3ee" },
  { id: "booked", label: "Booked", color: "#4ade80" },
  { id: "rejected", label: "Rejected", color: "#ef4444" },
] as const

const EVENTS = ["All events", "ADE 2025", "Thuishaven Summer", "Shelter Friday"] as const

// ---- Mock data (TODO: replace with SWR fetch from Supabase) ----
const MOCK: Record<string, PipelineArtist[]> = {
  pending: [
    { id: "azu", name: "Azu Tiwaline", imageUrl: null, genre: "Techno", status: "pending", composite: 61, targetEvent: null, aiMemoSnippet: "Steady regional growth but limited NL exposure so far.", assignedTo: "Lars", lastActivity: "3d ago" },
    { id: "dexphase", name: "DexPhase", imageUrl: null, genre: "Tech-House", status: "pending", composite: 42, targetEvent: null, aiMemoSnippet: "Early signals only — needs more data before evaluating.", assignedTo: null, lastActivity: "5d ago" },
  ],
  candidate: [
    { id: "verraco", name: "Verraco", imageUrl: null, genre: "Tech-House", status: "candidate", composite: 84, targetEvent: "ADE 2025 / Saturday Main Stage", aiMemoSnippet: "Strong momentum and excellent LOFI sound fit.", assignedTo: "Lars", lastActivity: "6h ago" },
    { id: "sansibar", name: "Sansibar", imageUrl: null, genre: "Afro House", status: "candidate", composite: 78, targetEvent: "Thuishaven Summer", aiMemoSnippet: "Rising Afro House act with growing festival presence.", assignedTo: "Mara", lastActivity: "1d ago" },
  ],
  accepted: [
    { id: "kettama", name: "KETTAMA", imageUrl: null, genre: "House", status: "accepted", composite: 71, targetEvent: "Shelter Friday", aiMemoSnippet: "Proven club draw, offer extended for autumn slot.", assignedTo: "Lars", lastActivity: "2d ago" },
  ],
  booked: [
    { id: "enrico", name: "Enrico Sangiuliano", imageUrl: null, genre: "Techno", status: "booked", composite: 88, targetEvent: "ADE 2025 / Main Stage", aiMemoSnippet: "Headline-tier techno, contract signed.", assignedTo: "Mara", lastActivity: "1w ago" },
  ],
  rejected: [
    { id: "noise", name: "Noisia Tribute", imageUrl: null, genre: "Drum & Bass", status: "rejected", composite: 34, targetEvent: null, aiMemoSnippet: "Genre mismatch for LOFI programming.", assignedTo: "Lars", lastActivity: "2w ago" },
  ],
}

const STATUS_DOT: Record<string, string> = {
  pending: "bg-slate-500",
  candidate: "bg-indigo-400",
  accepted: "bg-cyan-400",
  booked: "bg-green-400",
  rejected: "bg-red-400",
}

function scoreBadge(value: number | null): string {
  if (value === null) return "bg-slate-700 text-slate-300"
  if (value >= 65) return "bg-green-500/20 text-green-400"
  if (value >= 45) return "bg-amber-500/20 text-amber-400"
  return "bg-red-500/20 text-red-400"
}

function PipelineCard({ artist }: { artist: PipelineArtist }) {
  const firstLetter = artist.name.trim().charAt(0).toUpperCase() || "?"
  const initial = artist.assignedTo?.trim().charAt(0).toUpperCase()
  return (
    <div className="group flex gap-2 rounded-lg border border-white/5 bg-[#1e2535] p-3 transition-colors hover:border-[#6366f1]/40">
      <GripVertical size={16} className="mt-0.5 shrink-0 cursor-grab text-[#64748b] opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className="size-10 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10">
              {artist.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={artist.imageUrl || "/placeholder.svg"} alt={artist.name} crossOrigin="anonymous" className="size-full object-cover" />
              ) : (
                <div className="flex size-full items-center justify-center bg-gradient-to-br from-indigo-600 to-slate-800 text-sm font-bold text-white/90">
                  {firstLetter}
                </div>
              )}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-[#f1f5f9]">{artist.name}</p>
              <span className="inline-block rounded-full bg-white/5 px-1.5 py-0.5 text-[10px] text-[#94a3b8]">
                {artist.genre}
              </span>
            </div>
          </div>
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-bold ${scoreBadge(artist.composite)}`}>
            {artist.composite ?? "—"}
          </span>
        </div>

        {artist.targetEvent && (
          <p className="mt-2 truncate text-xs font-medium text-[#818cf8]">{artist.targetEvent}</p>
        )}

        {artist.aiMemoSnippet && (
          <p className="mt-1.5 truncate text-xs italic text-[#94a3b8]">{artist.aiMemoSnippet}</p>
        )}

        <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2">
          <div className="flex items-center gap-1.5">
            {initial ? (
              <span className="flex size-5 items-center justify-center rounded-full bg-[#6366f1] text-[10px] font-bold text-white">
                {initial}
              </span>
            ) : (
              <span className="flex size-5 items-center justify-center rounded-full bg-[#252d3f] text-[10px] text-[#64748b]">
                ?
              </span>
            )}
            <span className="text-[10px] text-[#64748b]">Last activity {artist.lastActivity}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function PipelinePage() {
  const [pipeline] = useState<Record<string, PipelineArtist[]>>(MOCK)
  const [assignFilter, setAssignFilter] = useState<"me" | "all">("all")
  const [eventFilter, setEventFilter] = useState<(typeof EVENTS)[number]>("All events")
  const [query, setQuery] = useState("")

  const filtered = useMemo(() => {
    const out: Record<string, PipelineArtist[]> = {}
    for (const col of COLUMNS) {
      out[col.id] = (pipeline[col.id] ?? []).filter((a) => {
        if (assignFilter === "me" && a.assignedTo !== "Lars") return false
        if (eventFilter !== "All events" && !(a.targetEvent ?? "").includes(eventFilter)) return false
        if (query && !a.name.toLowerCase().includes(query.toLowerCase())) return false
        return true
      })
    }
    return out
  }, [pipeline, assignFilter, eventFilter, query])

  function columnAverage(rows: PipelineArtist[]): number | null {
    const vals = rows.map((r) => r.composite).filter((v): v is number => v !== null)
    if (vals.length === 0) return null
    return Math.round(vals.reduce((s, v) => s + v, 0) / vals.length)
  }

  return (
    <div className="flex h-full flex-col gap-6">
      {/* HEADER */}
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-[#f1f5f9]">Booking Pipeline</h1>
        <p className="text-sm text-[#94a3b8]">Track every artist through the booking workflow</p>
      </header>

      {/* TOP ACTIONS */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-1 rounded-lg bg-[#1e2535] p-1">
          <button
            type="button"
            onClick={() => setAssignFilter("me")}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              assignFilter === "me" ? "bg-[#6366f1] text-white" : "text-[#94a3b8] hover:text-[#f1f5f9]"
            }`}
          >
            Assigned to me
          </button>
          <button
            type="button"
            onClick={() => setAssignFilter("all")}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              assignFilter === "all" ? "bg-[#6366f1] text-white" : "text-[#94a3b8] hover:text-[#f1f5f9]"
            }`}
          >
            All team
          </button>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative">
            <select
              value={eventFilter}
              onChange={(e) => setEventFilter(e.target.value as (typeof EVENTS)[number])}
              className="appearance-none rounded-lg border border-white/5 bg-[#1e2535] py-2 pl-3 pr-9 text-sm text-[#f1f5f9] focus:outline-none focus:ring-2 focus:ring-[#6366f1]/50"
            >
              {EVENTS.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#94a3b8]" />
          </div>

          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search artists…"
              className="w-full rounded-lg border border-white/5 bg-[#1e2535] py-2 pl-9 pr-3 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:outline-none focus:ring-2 focus:ring-[#6366f1]/50 sm:w-56"
            />
          </div>
        </div>
      </div>

      {/* KANBAN */}
      <div className="flex flex-1 gap-4 overflow-x-auto pb-2">
        {COLUMNS.map((col) => {
          const rows = filtered[col.id] ?? []
          const avg = columnAverage(rows)
          return (
            <div key={col.id} className="flex w-[300px] shrink-0 flex-col rounded-xl bg-[#161b27]">
              {/* Column header */}
              <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="size-2.5 rounded-full" style={{ backgroundColor: col.color }} />
                  <span className="font-semibold text-[#f1f5f9]" style={{ color: col.color }}>
                    {col.label}
                  </span>
                  <span className="rounded-full bg-[#1e2535] px-2 py-0.5 text-xs font-medium text-[#94a3b8]">
                    {rows.length}
                  </span>
                </div>
                <button
                  type="button"
                  aria-label={`Add artist to ${col.label}`}
                  className="inline-flex size-7 items-center justify-center rounded-md text-[#94a3b8] hover:bg-[#1e2535] hover:text-[#f1f5f9]"
                >
                  <Plus size={16} />
                </button>
              </div>

              {/* Cards */}
              <div className="flex flex-1 flex-col gap-2 p-3">
                {rows.length === 0 ? (
                  <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-white/10 text-xs text-[#64748b]">
                    Drag artists here
                  </div>
                ) : (
                  rows.map((a) => <PipelineCard key={a.id} artist={a} />)
                )}
              </div>

              {/* Column footer */}
              <div className="border-t border-white/5 px-4 py-2.5 text-xs text-[#94a3b8]">
                Avg composite: <span className="font-semibold text-[#f1f5f9]">{avg ?? "—"}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
