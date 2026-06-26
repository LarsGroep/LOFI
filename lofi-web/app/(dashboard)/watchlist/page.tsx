"use client"

import React, { useMemo, useState, useCallback } from "react"
import useSWR from "swr"
import {
  Star,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  TrendingUp,
  TrendingDown,
} from "lucide-react"
import type { ArtistListItem, ArtistStatus } from "@/types/supabase"

const fetcher = (url: string) => fetch(url).then(r => r.json())

const WATCHED_STATUSES: ArtistStatus[] = ["candidate", "accepted", "booked"]

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-slate-700 text-slate-300",
  candidate: "bg-indigo-500/20 text-indigo-400",
  accepted: "bg-cyan-500/20 text-cyan-400",
  booked: "bg-green-500/20 text-green-400",
  rejected: "bg-red-500/20 text-red-400",
}

const VERDICT_STYLES: Record<string, string> = {
  "Book Now": "bg-green-500/20 text-green-400",
  "Strong Watch": "bg-indigo-500/20 text-indigo-400",
  "Monitor": "bg-amber-500/20 text-amber-400",
  "Pass": "bg-slate-700 text-slate-400",
}

type SortKey = "name" | "status" | "lofiFitScore" | "xgboostGrowth90d" | "spMonthlyListeners" | "raEventCount"
type GroupBy = "none" | "status"

function scoreDot(value: number | null): string {
  if (value === null) return "bg-slate-600"
  if (value >= 65) return "bg-green-400"
  if (value >= 45) return "bg-amber-400"
  return "bg-red-400"
}

function fmtListeners(n: number | null): string {
  if (n == null) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

function SortHeader({
  label, col, sortKey, sortDir, onSort, align = "left",
}: {
  label: string; col: SortKey; sortKey: SortKey; sortDir: "asc" | "desc"
  onSort: (k: SortKey) => void; align?: "left" | "center"
}) {
  const active = sortKey === col
  return (
    <th className={`px-4 py-3 font-medium ${align === "center" ? "text-center" : "text-left"}`}>
      <button
        type="button"
        onClick={() => onSort(col)}
        className={`inline-flex items-center gap-1 transition-colors hover:text-[#f1f5f9] ${active ? "text-[#f1f5f9]" : ""} ${align === "center" ? "mx-auto" : ""}`}
      >
        {label}
        {active ? (sortDir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />) : <ArrowUpDown size={12} className="opacity-40" />}
      </button>
    </th>
  )
}

export default function WatchlistPage() {
  const { data, isLoading, error } = useSWR<ArtistListItem[]>('/api/artists?limit=500', fetcher, {
    revalidateOnFocus: false,
  })

  const [sortKey, setSortKey] = useState<SortKey>("lofiFitScore")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [groupBy, setGroupBy] = useState<GroupBy>("none")

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc")
    } else {
      setSortKey(key)
      setSortDir("desc")
    }
  }

  const watched = useMemo(() => {
    if (!data) return []
    return data.filter(a => (WATCHED_STATUSES as string[]).includes(a.status))
  }, [data])

  const sorted = useMemo(() => {
    const copy = [...watched]
    copy.sort((a, b) => {
      const av = a[sortKey] as string | number | null
      const bv = b[sortKey] as string | number | null
      if (av === null) return 1
      if (bv === null) return -1
      let cmp: number
      if (typeof av === "string" && typeof bv === "string") {
        cmp = av.localeCompare(bv)
      } else {
        cmp = (av as number) - (bv as number)
      }
      return sortDir === "asc" ? cmp : -cmp
    })
    return copy
  }, [watched, sortKey, sortDir])

  const groups = useMemo(() => {
    if (groupBy === "none") return [{ label: null as string | null, rows: sorted }]
    const map = new Map<string, ArtistListItem[]>()
    for (const a of sorted) {
      const key = a.status
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(a)
    }
    return Array.from(map.entries()).map(([label, rows]) => ({ label, rows }))
  }, [sorted, groupBy])

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <header>
          <h1 className="text-2xl font-bold text-[#f1f5f9]">Watchlist</h1>
          <p className="text-sm text-[#94a3b8]">Candidates, accepted & booked artists</p>
        </header>
        <div className="h-64 animate-pulse rounded-xl bg-[#161b27]" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-red-400">Failed to load watchlist.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-2xl font-bold text-[#f1f5f9]">Watchlist</h1>
            <p className="text-sm text-[#94a3b8]">Candidates, accepted & booked artists</p>
          </div>
          <span className="rounded-full bg-[#1e2535] px-2.5 py-1 text-xs font-medium text-[#94a3b8]">
            {watched.length} artists
          </span>
        </div>
        <div className="flex items-center gap-1 rounded-lg bg-[#1e2535] p-1">
          {(["none", "status"] as GroupBy[]).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGroupBy(g)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors ${groupBy === g ? "bg-[#6366f1] text-white" : "text-[#94a3b8] hover:text-[#f1f5f9]"}`}
            >
              {g === "none" ? "All" : "By status"}
            </button>
          ))}
        </div>
      </header>

      {watched.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-white/10 bg-[#161b27] p-16 text-center">
          <Star size={32} className="text-[#64748b]" />
          <p className="text-base font-medium text-[#f1f5f9]">No artists in candidate, accepted, or booked status</p>
          <a href="/dashboard" className="text-sm font-medium text-[#6366f1] hover:text-[#818cf8]">
            Browse artists to evaluate some
          </a>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-white/5 bg-[#161b27]">
          <table className="w-full min-w-[900px] text-sm">
            <thead>
              <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wide text-[#64748b]">
                <SortHeader label="Artist" col="name" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <SortHeader label="Status" col="status" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <th className="px-4 py-3 font-medium text-left">AI Verdict</th>
                <SortHeader label="LOFI Fit" col="lofiFitScore" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} align="center" />
                <SortHeader label="XGBoost 90d" col="xgboostGrowth90d" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} align="center" />
                <SortHeader label="Listeners" col="spMonthlyListeners" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} align="center" />
                <SortHeader label="RA Events" col="raEventCount" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} align="center" />
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <React.Fragment key={group.label ?? 'all'}>
                  {group.label && (
                    <tr>
                      <td colSpan={7} className="bg-[#1e2535]/50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[#94a3b8]">
                        {group.label} · {group.rows.length}
                      </td>
                    </tr>
                  )}
                  {group.rows.map((a) => {
                    const firstLetter = a.name.trim().charAt(0).toUpperCase() || "?"
                    const genre = a.genres?.[0] ?? ""
                    return (
                      <tr key={a.id} className="border-b border-white/5 transition-colors hover:bg-[#1e2535]">
                        <td className="px-4 py-3">
                          <a href={`/artist/${a.id}`} className="flex items-center gap-3 group">
                            <div className="size-8 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10">
                              {a.imageUrl ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={a.imageUrl} alt={a.name} crossOrigin="anonymous" className="size-full object-cover" />
                              ) : (
                                <div className="flex size-full items-center justify-center bg-gradient-to-br from-indigo-600 to-slate-800 text-xs font-bold text-white/90">
                                  {firstLetter}
                                </div>
                              )}
                            </div>
                            <div className="min-w-0">
                              <p className="truncate font-medium text-[#f1f5f9] group-hover:text-[#818cf8]">{a.name}</p>
                              {genre && <span className="text-xs text-[#94a3b8]">{genre}</span>}
                            </div>
                          </a>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[a.status] ?? STATUS_STYLES.pending}`}>
                            {a.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {a.verdict ? (
                            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${VERDICT_STYLES[a.verdict] ?? ""}`}>
                              {a.verdict}
                            </span>
                          ) : (
                            <span className="text-[#64748b] text-xs">No memo</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className="inline-flex items-center gap-1.5 font-medium text-[#f1f5f9]">
                            <span className={`size-2 rounded-full ${scoreDot(a.lofiFitScore)}`} />
                            {a.lofiFitScore != null ? Math.round(a.lofiFitScore) : "—"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-center">
                          {a.xgboostGrowth90d != null ? (
                            <span className="inline-flex items-center gap-1 text-[#f1f5f9]">
                              {(a.xgboostGrowth90d * 100).toFixed(1)}%
                              {a.xgboostGrowth90d >= 0.05
                                ? <TrendingUp size={13} className="text-green-400" />
                                : <TrendingDown size={13} className="text-red-400" />
                              }
                            </span>
                          ) : <span className="text-[#64748b]">—</span>}
                        </td>
                        <td className="px-4 py-3 text-center text-[#f1f5f9]">
                          {fmtListeners(a.spMonthlyListeners)}
                        </td>
                        <td className="px-4 py-3 text-center text-[#f1f5f9]">
                          {a.raEventCount ?? "—"}
                        </td>
                      </tr>
                    )
                  })}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
