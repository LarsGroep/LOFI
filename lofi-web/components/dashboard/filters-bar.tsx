"use client"

import { Search } from "lucide-react"

export type StatusFilter = "all" | "pending" | "candidate" | "accepted" | "booked"
export type SortKey = "composite" | "momentum" | "growth" | "name" | "recent"

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "candidate", label: "Candidate" },
  { value: "accepted", label: "Accepted" },
  { value: "booked", label: "Booked" },
]

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "composite", label: "Composite Score" },
  { value: "momentum", label: "Momentum" },
  { value: "growth", label: "Growth" },
  { value: "name", label: "Name" },
  { value: "recent", label: "Recent" },
]

interface FiltersBarProps {
  status: StatusFilter
  onStatusChange: (status: StatusFilter) => void
  sort: SortKey
  onSortChange: (sort: SortKey) => void
  search: string
  onSearchChange: (search: string) => void
}

export function FiltersBar({
  status,
  onStatusChange,
  sort,
  onSortChange,
  search,
  onSearchChange,
}: FiltersBarProps) {
  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      {/* Status chips */}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        {STATUS_OPTIONS.map((opt) => {
          const active = status === opt.value
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onStatusChange(opt.value)}
              aria-pressed={active}
              className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                active
                  ? "bg-indigo-500 text-white"
                  : "bg-[#1e2535] text-[#94a3b8] hover:text-[#f1f5f9]"
              }`}
            >
              {opt.label}
            </button>
          )
        })}
      </div>

      <div className="flex items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 lg:w-64 lg:flex-none">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#94a3b8]"
            size={16}
            aria-hidden="true"
          />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search artists"
            aria-label="Search artists"
            className="w-full rounded-lg border border-[#1e2535] bg-[#161b27] py-2 pl-9 pr-3 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:border-indigo-500 focus:outline-none"
          />
        </div>

        {/* Sort */}
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value as SortKey)}
          aria-label="Sort artists"
          className="rounded-lg border border-[#1e2535] bg-[#161b27] py-2 pl-3 pr-8 text-sm text-[#f1f5f9] focus:border-indigo-500 focus:outline-none"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
