"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { Search, X } from "lucide-react"

interface SearchResult {
  id: string
  name: string
  status: string
  imageUrl: string | null
  genres: string[] | null
  spMonthlyListeners: number | null
}

const STATUS_DOT: Record<string, string> = {
  booked:    "bg-green-400",
  accepted:  "bg-cyan-400",
  candidate: "bg-indigo-400",
  pending:   "bg-slate-500",
  rejected:  "bg-red-400",
}

function fmt(n: number | null | undefined): string {
  if (n == null) return ""
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(Math.round(n))
}

export function GlobalSearch() {
  const router = useRouter()
  const [value, setValue] = useState("")
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)

  const runSearch = useCallback(async (q: string) => {
    if (!q.trim() || q.length < 2) { setResults([]); setOpen(false); return }
    try {
      const res = await fetch(`/api/artists/search?q=${encodeURIComponent(q)}&limit=8`)
      if (!res.ok) return
      const data: SearchResult[] = await res.json()
      setResults(data)
      setOpen(data.length > 0)
      setSelected(-1)
    } catch {
      // silently ignore
    }
  }, [])

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const next = e.target.value
    setValue(next)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!next.trim()) { setResults([]); setOpen(false); return }
    debounceRef.current = setTimeout(() => runSearch(next), 220)
  }

  function navigateTo(id: string) {
    router.push(`/artist/${id}`)
    setValue("")
    setResults([])
    setOpen(false)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setSelected(prev => Math.min(prev + 1, results.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setSelected(prev => Math.max(prev - 1, -1))
    } else if (e.key === "Enter") {
      if (selected >= 0 && results[selected]) {
        navigateTo(results[selected].id)
      } else if (value.trim()) {
        router.push(`/dashboard?q=${encodeURIComponent(value.trim())}`)
        setOpen(false)
      }
    } else if (e.key === "Escape") {
      setValue("")
      setResults([])
      setOpen(false)
    }
  }

  function clearSearch() {
    setValue("")
    setResults([])
    setOpen(false)
  }

  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", onMouseDown)
    return () => document.removeEventListener("mousedown", onMouseDown)
  }, [])

  useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current) }, [])

  return (
    <div ref={wrapperRef} className="relative w-full max-w-md">
      <Search
        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[#64748b]"
        aria-hidden="true"
      />
      <input
        type="search"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={() => { if (results.length > 0) setOpen(true) }}
        placeholder="Search artists, genres, scenes..."
        aria-label="Search"
        className="h-9 w-full rounded-md border border-[#1e2535] bg-[#161b27] pl-9 pr-8 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:border-[#6366f1] focus:outline-none focus:ring-1 focus:ring-[#6366f1]"
      />
      {value && (
        <button
          type="button"
          onClick={clearSearch}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#64748b] transition-colors hover:text-[#94a3b8]"
          aria-label="Clear search"
        >
          <X size={14} />
        </button>
      )}

      {open && results.length > 0 && (
        <div className="absolute top-full z-50 mt-1.5 w-full overflow-hidden rounded-xl border border-[#1e2535] bg-[#0e1117] shadow-2xl">
          {results.map((r, i) => (
            <button
              key={r.id}
              type="button"
              onClick={() => navigateTo(r.id)}
              className={`flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-[#161b27] ${selected === i ? "bg-[#161b27]" : ""}`}
            >
              {/* Avatar */}
              <div className="relative size-9 shrink-0 overflow-hidden rounded-full bg-[#1e2535]">
                {r.imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={r.imageUrl} alt={r.name} className="size-full object-cover" crossOrigin="anonymous" />
                ) : (
                  <div className="flex size-full items-center justify-center text-xs font-bold text-[#818cf8]">
                    {r.name.charAt(0)}
                  </div>
                )}
                <span className={`absolute bottom-0 right-0 size-2.5 rounded-full border border-[#0e1117] ${STATUS_DOT[r.status] ?? "bg-slate-500"}`} />
              </div>

              {/* Info */}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[#f1f5f9]">{r.name}</p>
                <p className="truncate text-xs text-[#64748b]">
                  {r.genres?.slice(0, 2).join(" · ") || "—"}
                  {r.spMonthlyListeners ? ` · ${fmt(r.spMonthlyListeners)} listeners` : ""}
                </p>
              </div>

              {/* Status label */}
              <span className="shrink-0 text-xs capitalize text-[#64748b]">{r.status}</span>
            </button>
          ))}

          {/* Fallback: search all */}
          <button
            type="button"
            onClick={() => { router.push(`/dashboard?q=${encodeURIComponent(value.trim())}`); setOpen(false) }}
            className="flex w-full items-center gap-2 border-t border-[#1e2535] px-3 py-2 text-xs text-[#64748b] transition-colors hover:text-[#94a3b8]"
          >
            <Search size={11} />
            Search all artists for &ldquo;{value}&rdquo;
          </button>
        </div>
      )}
    </div>
  )
}
