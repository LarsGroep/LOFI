'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { Search, Users, Music, TrendingUp, Star } from 'lucide-react'
import type { ArtistListItem } from '@/types/supabase'

const fetcher = (url: string) => fetch(url).then(r => r.json())

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 999_500) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}K`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(Math.round(n))
}

const VERDICT_COLORS: Record<string, string> = {
  'Book Now': 'bg-green-500/15 text-green-400',
  'Strong Watch': 'bg-indigo-500/15 text-indigo-400',
  'Monitor': 'bg-amber-500/15 text-amber-400',
  'Pass': 'bg-slate-700 text-slate-400',
}

const STATUS_COLORS: Record<string, string> = {
  booked: 'bg-green-500/20 text-green-400',
  accepted: 'bg-cyan-500/20 text-cyan-400',
  candidate: 'bg-indigo-500/20 text-indigo-400',
  pending: 'bg-slate-700 text-slate-300',
}

interface Rec {
  artistId: string
  name: string
  status: string
  imageUrl: string | null
  genres: string[] | null
  spMonthlyListeners: number | null
  bookingAgent: string | null
  xgboostGrowth90d: number | null
  verdict: string | null
  coCount: number
  sharedVenues: string[]
  sharedCities: string[]
  latestSharedEvent: string
  isOnLofiRoster: boolean
}

export default function RecommendationsPage() {
  const router = useRouter()
  const [search, setSearch] = useState('')
  const [selectedArtist, setSelectedArtist] = useState<{ id: string; name: string } | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)

  // Artist search
  const { data: searchResults } = useSWR<ArtistListItem[]>(
    search.length >= 2 ? `/api/artists/search?q=${encodeURIComponent(search)}` : null,
    fetcher, { revalidateOnFocus: false }
  )

  // Recommendations for selected artist
  const { data: recsData, isLoading } = useSWR<{ recommendations: Rec[]; totalEvents: number; artistName: string }>(
    selectedArtist ? `/api/recommendations?artist_id=${selectedArtist.id}&limit=20` : null,
    fetcher, { revalidateOnFocus: false }
  )

  const handleSelect = useCallback((artist: { id: string; name: string }) => {
    setSelectedArtist(artist)
    setSearch('')
    setSearchOpen(false)
  }, [])

  const recs = recsData?.recommendations ?? []

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-[#f1f5f9]">Artist Recommender</h1>
        <p className="text-sm text-[#94a3b8]">Find artists who frequently share lineups with a target artist</p>
      </div>

      {/* Artist picker */}
      <div className="mt-6 relative">
        <div
          className="flex items-center gap-3 rounded-xl border border-[#1e2535] bg-[#161b27] p-4 cursor-pointer"
          onClick={() => setSearchOpen(true)}
        >
          {selectedArtist ? (
            <>
              <Users size={18} className="shrink-0 text-[#6366f1]" />
              <span className="text-[#f1f5f9] font-medium">{selectedArtist.name}</span>
              <button
                type="button"
                onClick={e => { e.stopPropagation(); setSelectedArtist(null) }}
                className="ml-auto text-xs text-[#64748b] hover:text-[#f1f5f9]"
              >
                Change
              </button>
            </>
          ) : (
            <>
              <Search size={18} className="shrink-0 text-[#64748b]" />
              <span className="text-[#64748b]">Search for an artist to find booking recommendations…</span>
            </>
          )}
        </div>

        {/* Dropdown search */}
        {(searchOpen || search.length > 0) && (
          <div className="absolute top-full left-0 right-0 z-20 mt-1 overflow-hidden rounded-xl border border-[#1e2535] bg-[#161b27] shadow-2xl">
            <div className="p-3 border-b border-[#1e2535]">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]" />
                <input
                  autoFocus
                  type="text"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  onKeyDown={e => e.key === 'Escape' && setSearchOpen(false)}
                  placeholder="Type artist name…"
                  className="w-full rounded-lg bg-[#1e2535] pl-8 pr-3 py-2 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:outline-none"
                />
              </div>
            </div>
            {searchResults?.length ? (
              <ul className="max-h-72 overflow-y-auto divide-y divide-[#1e2535]">
                {searchResults.map(a => (
                  <li key={a.id}>
                    <button
                      type="button"
                      onClick={() => handleSelect({ id: a.id, name: a.name })}
                      className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-[#1e2535] transition-colors"
                    >
                      {a.imageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={a.imageUrl} alt={a.name} className="size-8 rounded-full object-cover" />
                      ) : (
                        <div className="flex size-8 items-center justify-center rounded-full bg-[#1e2535] text-xs font-bold text-[#818cf8]">
                          {a.name.charAt(0)}
                        </div>
                      )}
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-[#f1f5f9]">{a.name}</p>
                        <p className="text-xs text-[#64748b] capitalize">{a.status} · {(a.genres ?? []).slice(0, 2).join(', ')}</p>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            ) : search.length >= 2 ? (
              <p className="px-4 py-6 text-center text-sm text-[#64748b]">No artists found</p>
            ) : (
              <p className="px-4 py-6 text-center text-sm text-[#64748b]">Start typing to search…</p>
            )}
          </div>
        )}
      </div>

      {/* Results */}
      {selectedArtist && (
        <div className="mt-6">
          {isLoading ? (
            <div className="flex flex-col gap-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-20 animate-pulse rounded-xl bg-[#161b27]" />
              ))}
            </div>
          ) : recs.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <Music size={32} className="text-[#64748b]" />
              <p className="text-sm text-[#64748b]">No co-lineup data found for {selectedArtist.name}</p>
              <p className="text-xs text-[#475569]">This artist may not have RA events tracked yet.</p>
            </div>
          ) : (
            <>
              <div className="mb-4 flex items-center justify-between">
                <p className="text-sm text-[#94a3b8]">
                  {recs.length} recommendations · based on {recsData?.totalEvents ?? 0} tracked events
                </p>
              </div>
              <div className="flex flex-col gap-3">
                {recs.map((rec, i) => (
                  <div
                    key={rec.artistId}
                    className="flex items-center gap-4 rounded-xl border border-[#1e2535] bg-[#161b27] p-4 transition hover:border-[#6366f1]/30"
                  >
                    {/* Rank */}
                    <span className="w-6 shrink-0 text-center text-sm font-semibold text-[#64748b]">{i + 1}</span>

                    {/* Image */}
                    <button type="button" onClick={() => router.push(`/artist/${rec.artistId}`)}>
                      {rec.imageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={rec.imageUrl} alt={rec.name} className="size-12 rounded-full object-cover ring-2 ring-white/10" />
                      ) : (
                        <div className="flex size-12 items-center justify-center rounded-full bg-gradient-to-br from-indigo-600 to-slate-800 text-lg font-bold text-white ring-2 ring-white/10">
                          {rec.name.charAt(0)}
                        </div>
                      )}
                    </button>

                    {/* Info */}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => router.push(`/artist/${rec.artistId}`)}
                          className="text-sm font-semibold text-[#f1f5f9] hover:text-indigo-300"
                        >
                          {rec.name}
                        </button>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${STATUS_COLORS[rec.status] ?? 'bg-slate-700 text-slate-300'}`}>
                          {rec.status}
                        </span>
                        {rec.isOnLofiRoster && (
                          <span className="flex items-center gap-0.5 rounded-full bg-green-500/10 px-2 py-0.5 text-[10px] text-green-400">
                            <Star size={9} className="fill-green-400" /> LOFI booked
                          </span>
                        )}
                        {rec.verdict && (
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${VERDICT_COLORS[rec.verdict] ?? ''}`}>
                            {rec.verdict}
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs text-[#64748b]">
                        {(rec.genres ?? []).slice(0, 2).join(', ')}
                        {rec.bookingAgent ? ` · ${rec.bookingAgent}` : ''}
                      </p>
                      <p className="mt-0.5 text-xs text-[#475569]">
                        Shared venues: {rec.sharedVenues.join(', ') || '—'}
                        {rec.sharedCities.length ? ` · ${rec.sharedCities.join(', ')}` : ''}
                      </p>
                    </div>

                    {/* Stats */}
                    <div className="hidden shrink-0 flex-col items-end gap-1 sm:flex">
                      <span className="text-xs text-[#64748b]">{fmt(rec.spMonthlyListeners)} listeners</span>
                      {rec.xgboostGrowth90d != null && (
                        <span className={`flex items-center gap-1 text-xs font-medium ${rec.xgboostGrowth90d > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          <TrendingUp size={11} />
                          {rec.xgboostGrowth90d >= 0 ? '+' : ''}{(rec.xgboostGrowth90d * 100).toFixed(1)}%
                        </span>
                      )}
                    </div>

                    {/* Co-count badge */}
                    <div className="shrink-0 flex flex-col items-center justify-center rounded-lg bg-indigo-500/10 px-3 py-2 text-center">
                      <span className="text-lg font-bold text-indigo-300">{rec.coCount}</span>
                      <span className="text-[9px] uppercase tracking-wide text-[#64748b]">co-shows</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Empty state */}
      {!selectedArtist && !searchOpen && (
        <div className="mt-16 flex flex-col items-center gap-4 text-center">
          <div className="flex size-16 items-center justify-center rounded-full bg-indigo-500/10">
            <Users size={28} className="text-indigo-400" />
          </div>
          <div>
            <p className="text-sm font-medium text-[#f1f5f9]">Select an artist to get recommendations</p>
            <p className="mt-1 text-sm text-[#64748b]">We'll find artists who share the most lineups on Resident Advisor</p>
          </div>
        </div>
      )}
    </div>
  )
}
