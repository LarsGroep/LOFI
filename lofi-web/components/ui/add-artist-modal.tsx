'use client'

import { useState, useEffect, useRef } from 'react'
import { Search, X, Plus, CheckCircle2, ExternalLink } from 'lucide-react'
import useSWR from 'swr'

const fetcher = (url: string) => fetch(url).then(r => r.json())

interface SearchResult {
  id: string
  name: string
  status: string
  imageUrl: string | null
  genres: string[] | null
  spMonthlyListeners: number | null
}

function fmt(n: number | null | undefined): string {
  if (n == null) return ''
  if (n >= 999_500) return `${(n / 1_000_000).toFixed(1)}M listeners`
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}K listeners`
  return `${n.toLocaleString()} listeners`
}

const STATUS_COLORS: Record<string, string> = {
  booked: 'bg-green-500/20 text-green-400',
  accepted: 'bg-cyan-500/20 text-cyan-400',
  candidate: 'bg-indigo-500/20 text-indigo-400',
  pending: 'bg-slate-700 text-slate-300',
}

export function AddArtistModal({ onClose, onNavigate }: { onClose: () => void; onNavigate: (id: string) => void }) {
  const [query, setQuery] = useState('')
  const [addedToQueue, setAddedToQueue] = useState(false)
  const [adding, setAdding] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const { data: results, isLoading } = useSWR<SearchResult[]>(
    query.trim().length >= 2 ? `/api/artists/search?q=${encodeURIComponent(query.trim())}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 300 }
  )

  async function handleAddToQueue() {
    if (!query.trim()) return
    setAdding(true)
    try {
      await fetch('/api/artists/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: query.trim(), source: 'manual' }),
      })
      setAddedToQueue(true)
    } finally {
      setAdding(false)
    }
  }

  const noResults = !isLoading && query.trim().length >= 2 && (results ?? []).length === 0

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-[#1e2535] bg-[#161b27] shadow-2xl">
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-[#1e2535] px-4 py-3">
          <Search size={16} className="shrink-0 text-[#64748b]" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => { setQuery(e.target.value); setAddedToQueue(false) }}
            placeholder="Search artist by name…"
            className="flex-1 bg-transparent text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:outline-none"
          />
          <button type="button" onClick={onClose} className="shrink-0 text-[#64748b] hover:text-[#f1f5f9]">
            <X size={16} />
          </button>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto">
          {query.trim().length < 2 ? (
            <p className="px-4 py-8 text-center text-sm text-[#64748b]">Type at least 2 characters to search</p>
          ) : isLoading ? (
            <div className="flex flex-col divide-y divide-[#1e2535]">
              {[1, 2, 3].map(i => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <div className="size-10 animate-pulse rounded-full bg-[#1e2535]" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3 w-32 animate-pulse rounded bg-[#1e2535]" />
                    <div className="h-2 w-20 animate-pulse rounded bg-[#1e2535]" />
                  </div>
                </div>
              ))}
            </div>
          ) : (results ?? []).length > 0 ? (
            <ul className="divide-y divide-[#1e2535]">
              {results!.map(a => (
                <li key={a.id}>
                  <button
                    type="button"
                    onClick={() => { onNavigate(a.id); onClose() }}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-[#1e2535]"
                  >
                    {a.imageUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={a.imageUrl} alt={a.name} className="size-10 rounded-full object-cover" />
                    ) : (
                      <div className="flex size-10 items-center justify-center rounded-full bg-gradient-to-br from-indigo-600 to-slate-800 text-sm font-bold text-white">
                        {a.name.charAt(0)}
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[#f1f5f9]">{a.name}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${STATUS_COLORS[a.status] ?? 'bg-slate-700 text-slate-300'}`}>
                          {a.status}
                        </span>
                      </div>
                      <p className="text-xs text-[#64748b]">
                        {(a.genres ?? []).slice(0, 2).join(', ')}
                        {a.spMonthlyListeners ? ` · ${fmt(a.spMonthlyListeners)}` : ''}
                      </p>
                    </div>
                    <ExternalLink size={14} className="shrink-0 text-[#64748b]" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {/* Add to queue footer — shown when no exact match */}
        {noResults && (
          <div className="border-t border-[#1e2535] px-4 py-4">
            {addedToQueue ? (
              <div className="flex items-center gap-2 text-sm text-emerald-400">
                <CheckCircle2 size={16} />
                <span><strong>{query.trim()}</strong> added to discovery queue. It will be scraped on the next run.</span>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-[#f1f5f9]">"{query.trim()}" not in database</p>
                  <p className="text-xs text-[#64748b]">Add to discovery queue for next scrape cycle</p>
                </div>
                <button
                  type="button"
                  onClick={handleAddToQueue}
                  disabled={adding}
                  className="flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-60"
                >
                  <Plus size={14} />
                  {adding ? 'Adding…' : 'Add to Queue'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
