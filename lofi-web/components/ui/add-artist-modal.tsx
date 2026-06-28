'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { Search, X, Plus, CheckCircle2, AlertCircle, Music2, ChevronRight } from 'lucide-react'

function fmt(n: number | null | undefined): string {
  if (n == null) return ''
  if (n >= 999_500) return `${(n / 1_000_000).toFixed(1)}M listeners`
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}K listeners`
  return `${n.toLocaleString()} listeners`
}

interface LocalResult {
  id: string
  name: string
  status: string
  imageUrl: string | null
  genres: string[] | null
  spMonthlyListeners: number | null
}

interface CmResult {
  id: number
  name: string
  image_url: string | null
  genres: string[]
  sp_monthly_listeners: number | null
  cm_artist_score: number | null
  city: string | null
  country: string | null
}

type Step = 'search' | 'cm-disambig' | 'queued'

const STATUS_COLORS: Record<string, string> = {
  booked:    'bg-green-500/20 text-green-400',
  accepted:  'bg-cyan-500/20 text-cyan-400',
  candidate: 'bg-indigo-500/20 text-indigo-400',
  pending:   'bg-slate-700 text-slate-300',
}

export function AddArtistModal({ onClose, onNavigate }: { onClose: () => void; onNavigate: (id: string) => void }) {
  const [query, setQuery] = useState('')
  const [step, setStep] = useState<Step>('search')
  const [localResults, setLocalResults] = useState<LocalResult[]>([])
  const [cmResults, setCmResults] = useState<CmResult[]>([])
  const [localLoading, setLocalLoading] = useState(false)
  const [cmLoading, setCmLoading] = useState(false)
  const [cmError, setCmError] = useState<string | null>(null)
  const [queued, setQueued] = useState<{ name: string } | null>(null)
  const [adding, setAdding] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { inputRef.current?.focus() }, [])
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const runSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) { setLocalResults([]); return }
    setLocalLoading(true)
    try {
      const res = await fetch(`/api/artists/search?q=${encodeURIComponent(q.trim())}`)
      if (res.ok) setLocalResults(await res.json())
    } finally {
      setLocalLoading(false)
    }
  }, [])

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value
    setQuery(v)
    setStep('search')
    setCmResults([])
    setCmError(null)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => runSearch(v), 280)
  }

  async function searchChartmetric() {
    if (!query.trim()) return
    setCmLoading(true)
    setCmError(null)
    setStep('cm-disambig')
    try {
      const res = await fetch(`/api/artists/chartmetric-search?q=${encodeURIComponent(query.trim())}`)
      const data = await res.json()
      if (!res.ok) {
        setCmError(data.error ?? 'Search failed')
        setCmResults([])
      } else {
        setCmResults(data)
      }
    } finally {
      setCmLoading(false)
    }
  }

  async function addCmArtist(artist: CmResult) {
    setAdding(true)
    try {
      await fetch('/api/artists/chartmetric-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cm_artist_id: artist.id, name: artist.name }),
      })
      setQueued({ name: artist.name })
      setStep('queued')
    } finally {
      setAdding(false)
    }
  }

  async function addManual() {
    if (!query.trim()) return
    setAdding(true)
    try {
      await fetch('/api/artists/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: query.trim(), source: 'manual' }),
      })
      setQueued({ name: query.trim() })
      setStep('queued')
    } finally {
      setAdding(false)
    }
  }

  const noLocalResults = !localLoading && query.trim().length >= 2 && localResults.length === 0

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] px-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-[#1e2535] bg-[#161b27] shadow-2xl">

        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-[#1e2535] px-4 py-3">
          <Search size={16} className="shrink-0 text-[#64748b]" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={handleChange}
            placeholder="Search artist by name…"
            className="flex-1 bg-transparent text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:outline-none"
          />
          <button type="button" onClick={onClose} className="shrink-0 text-[#64748b] hover:text-[#f1f5f9]"><X size={16} /></button>
        </div>

        {/* STEP: search — local DB results */}
        {step === 'search' && (
          <div className="max-h-80 overflow-y-auto">
            {query.trim().length < 2 ? (
              <p className="px-4 py-8 text-center text-sm text-[#64748b]">Type at least 2 characters to search</p>
            ) : localLoading ? (
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
            ) : localResults.length > 0 ? (
              <ul className="divide-y divide-[#1e2535]">
                {localResults.map(a => (
                  <li key={a.id}>
                    <button type="button" onClick={() => { onNavigate(a.id); onClose() }}
                      className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-[#1e2535]">
                      {a.imageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={a.imageUrl} alt={a.name} className="size-10 rounded-full object-cover" crossOrigin="anonymous" />
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
                      <ChevronRight size={14} className="shrink-0 text-[#64748b]" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )}

        {/* STEP: Chartmetric disambiguation */}
        {step === 'cm-disambig' && (
          <div className="max-h-80 overflow-y-auto">
            {cmLoading ? (
              <div className="flex flex-col gap-3 p-4">
                <p className="text-xs text-[#64748b]">Searching Chartmetric for &ldquo;{query}&rdquo;…</p>
                {[1, 2, 3].map(i => <div key={i} className="h-14 animate-pulse rounded-lg bg-[#1e2535]" />)}
              </div>
            ) : cmError ? (
              <div className="p-6">
                <div className="flex items-start gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                  <AlertCircle size={15} className="mt-0.5 shrink-0 text-amber-400" />
                  <div>
                    <p className="text-sm font-medium text-amber-300">Chartmetric unavailable</p>
                    <p className="mt-1 text-xs text-[#94a3b8]">{cmError}</p>
                    <p className="mt-2 text-xs text-[#64748b]">You can still add &ldquo;{query}&rdquo; to the discovery queue manually.</p>
                  </div>
                </div>
                <button type="button" onClick={addManual} disabled={adding}
                  className="mt-3 w-full rounded-lg bg-[#1e2535] px-4 py-2.5 text-sm text-[#f1f5f9] hover:bg-[#2a3347] transition-colors disabled:opacity-50">
                  {adding ? 'Adding…' : `Add "${query}" to queue anyway`}
                </button>
              </div>
            ) : cmResults.length === 0 ? (
              <div className="p-6 text-center">
                <p className="text-sm text-[#f1f5f9]">No results on Chartmetric for &ldquo;{query}&rdquo;</p>
                <p className="mt-1 text-xs text-[#64748b]">You can still add them to the discovery queue</p>
                <button type="button" onClick={addManual} disabled={adding}
                  className="mt-3 rounded-lg bg-[#1e2535] px-4 py-2 text-sm text-[#f1f5f9] hover:bg-[#2a3347] transition-colors disabled:opacity-50">
                  {adding ? 'Adding…' : 'Add to queue'}
                </button>
              </div>
            ) : (
              <div>
                <p className="px-4 pt-3 pb-2 text-xs font-medium text-[#94a3b8]">
                  Which artist did you mean? — {cmResults.length} results on Chartmetric
                </p>
                <ul className="divide-y divide-[#1e2535]">
                  {cmResults.map(a => (
                    <li key={a.id}>
                      <button type="button" onClick={() => addCmArtist(a)} disabled={adding}
                        className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-[#1e2535] disabled:opacity-50">
                        {a.image_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={a.image_url} alt={a.name} className="size-10 rounded-full object-cover" crossOrigin="anonymous" />
                        ) : (
                          <div className="flex size-10 items-center justify-center rounded-full bg-gradient-to-br from-indigo-600 to-slate-800 text-sm font-bold text-white">
                            <Music2 size={16} />
                          </div>
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-[#f1f5f9]">{a.name}</p>
                          <p className="text-xs text-[#64748b]">
                            {a.genres.slice(0, 2).join(', ')}
                            {a.city ? ` · ${a.city}${a.country ? `, ${a.country}` : ''}` : ''}
                            {a.sp_monthly_listeners ? ` · ${fmt(a.sp_monthly_listeners)}` : ''}
                            {a.cm_artist_score != null ? ` · CM ${a.cm_artist_score.toFixed(0)}` : ''}
                          </p>
                        </div>
                        <Plus size={14} className="shrink-0 text-indigo-400" />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* STEP: success */}
        {step === 'queued' && (
          <div className="p-6 text-center">
            <CheckCircle2 size={32} className="mx-auto mb-3 text-emerald-400" />
            <p className="text-sm font-semibold text-[#f1f5f9]">{queued?.name} added to queue</p>
            <p className="mt-1 text-xs text-[#64748b]">The artist will be scraped and enriched on the next pipeline run.</p>
            <button type="button" onClick={onClose}
              className="mt-4 rounded-lg bg-[#1e2535] px-4 py-2 text-sm text-[#f1f5f9] hover:bg-[#2a3347] transition-colors">
              Close
            </button>
          </div>
        )}

        {/* Footer — shown only in search step when no local results */}
        {step === 'search' && noLocalResults && (
          <div className="border-t border-[#1e2535] px-4 py-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-[#f1f5f9]">&ldquo;{query.trim()}&rdquo; not in database</p>
                <p className="text-xs text-[#64748b]">Search Chartmetric to find the right artist</p>
              </div>
              <button type="button" onClick={searchChartmetric}
                className="flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-400 transition-colors">
                <Search size={13} /> Find on Chartmetric
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
