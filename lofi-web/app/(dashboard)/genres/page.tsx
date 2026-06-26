'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import type { ArtistListItem } from '@/types/supabase'

const fetcher = (url: string) => fetch(url).then(r => r.json())

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 999_500) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}K`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(Math.round(n))
}

interface GenreRow {
  name: string
  artistCount: number
  avgListeners: number
  avgGrowth: number | null
}

const VERDICT_COLORS: Record<string, string> = {
  'Book Now': 'bg-green-500/15 text-green-400',
  'Strong Watch': 'bg-indigo-500/15 text-indigo-400',
  'Monitor': 'bg-amber-500/15 text-amber-400',
  'Pass': 'bg-slate-700 text-slate-300',
}

function GrowthBadge({ v }: { v: number | null }) {
  if (v == null) return <Minus size={12} className="text-[#64748b]" />
  if (v > 0.02) return <span className="flex items-center gap-0.5 text-xs font-semibold text-emerald-400"><TrendingUp size={11} />+{(v * 100).toFixed(1)}%</span>
  if (v < -0.02) return <span className="flex items-center gap-0.5 text-xs font-semibold text-rose-400"><TrendingDown size={11} />{(v * 100).toFixed(1)}%</span>
  return <span className="text-xs text-[#94a3b8]">{v >= 0 ? '+' : ''}{(v * 100).toFixed(1)}%</span>
}

export default function GenresPage() {
  const router = useRouter()
  const [selectedGenre, setSelectedGenre] = useState<string | null>(null)
  const [artistSort, setArtistSort] = useState<'xgboostGrowth90d' | 'spMonthlyListeners'>('xgboostGrowth90d')

  const { data: sceneData, isLoading: sceneLoading } = useSWR<{ genres: GenreRow[] }>(
    '/api/scene', fetcher, { revalidateOnFocus: false }
  )

  const { data: artists, isLoading: artistsLoading } = useSWR<ArtistListItem[]>(
    selectedGenre ? `/api/artists?genre=${encodeURIComponent(selectedGenre)}&limit=500` : null,
    fetcher, { revalidateOnFocus: false }
  )

  const genres = sceneData?.genres ?? []

  const sortedArtists = [...(artists ?? [])].sort((a, b) =>
    ((b[artistSort] as number | null) ?? -Infinity) - ((a[artistSort] as number | null) ?? -Infinity)
  )

  return (
    <div className="mx-auto max-w-7xl">
      <div>
        <h1 className="text-2xl font-semibold text-[#f1f5f9]">Genre Explorer</h1>
        <p className="mt-1 text-sm text-[#94a3b8]">
          Browse artists by genre · {genres.length} genres tracked
        </p>
      </div>

      {/* Genre chips */}
      <div className="mt-6 flex flex-wrap gap-2">
        {sceneLoading ? (
          Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="h-8 w-24 animate-pulse rounded-full bg-[#161b27]" />
          ))
        ) : (
          genres.map(g => {
            const isSelected = selectedGenre === g.name
            const growth = g.avgGrowth
            return (
              <button
                key={g.name}
                type="button"
                onClick={() => setSelectedGenre(isSelected ? null : g.name)}
                className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium capitalize transition-all ${
                  isSelected
                    ? 'border-[#6366f1] bg-[#6366f1] text-white'
                    : 'border-[#1e2535] bg-[#161b27] text-[#94a3b8] hover:border-[#6366f1]/40 hover:text-[#f1f5f9]'
                }`}
              >
                {g.name}
                <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${isSelected ? 'bg-white/20 text-white' : 'bg-[#1e2535] text-[#64748b]'}`}>
                  {g.artistCount}
                </span>
                {growth != null && (
                  <span className={`text-[10px] font-semibold ${growth > 0.02 ? (isSelected ? 'text-green-200' : 'text-emerald-400') : growth < -0.02 ? (isSelected ? 'text-red-200' : 'text-rose-400') : 'text-[#64748b]'}`}>
                    {growth >= 0 ? '+' : ''}{(growth * 100).toFixed(0)}%
                  </span>
                )}
              </button>
            )
          })
        )}
      </div>

      {/* Artist grid for selected genre */}
      {selectedGenre && (
        <div className="mt-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold capitalize text-[#f1f5f9]">{selectedGenre}</h2>
              {!artistsLoading && (
                <p className="text-sm text-[#94a3b8]">{sortedArtists.length} artists</p>
              )}
            </div>
            <div className="flex gap-1 rounded-lg border border-[#1e2535] bg-[#161b27] p-0.5">
              <button
                type="button"
                onClick={() => setArtistSort('xgboostGrowth90d')}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${artistSort === 'xgboostGrowth90d' ? 'bg-[#6366f1] text-white' : 'text-[#94a3b8] hover:text-[#f1f5f9]'}`}
              >
                By Growth
              </button>
              <button
                type="button"
                onClick={() => setArtistSort('spMonthlyListeners')}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${artistSort === 'spMonthlyListeners' ? 'bg-[#6366f1] text-white' : 'text-[#94a3b8] hover:text-[#f1f5f9]'}`}
              >
                By Listeners
              </button>
            </div>
          </div>

          {artistsLoading ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {Array.from({ length: 10 }).map((_, i) => (
                <div key={i} className="h-48 animate-pulse rounded-xl bg-[#161b27]" />
              ))}
            </div>
          ) : sortedArtists.length === 0 ? (
            <div className="py-16 text-center text-sm text-[#64748b]">No artists found for this genre.</div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {sortedArtists.map((a, i) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => router.push(`/artist/${a.id}`)}
                  className="group flex flex-col overflow-hidden rounded-xl border border-[#1e2535] bg-[#161b27] text-left transition hover:border-[#6366f1]/40 hover:shadow-lg"
                >
                  <div className="relative aspect-square w-full overflow-hidden bg-[#1e2535]">
                    {a.imageUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={a.imageUrl} alt={a.name} className="size-full object-cover transition-transform duration-300 group-hover:scale-105" />
                    ) : (
                      <div className="flex size-full items-center justify-center bg-gradient-to-br from-indigo-600/40 to-slate-800">
                        <span className="text-4xl font-bold text-white/30">{a.name.charAt(0)}</span>
                      </div>
                    )}
                    {/* Rank badge */}
                    <span className="absolute left-2 top-2 flex size-6 items-center justify-center rounded-full bg-black/60 text-[10px] font-bold text-white">
                      {i + 1}
                    </span>
                    {/* Growth badge */}
                    {a.xgboostGrowth90d != null && (
                      <span className={`absolute right-2 top-2 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                        a.xgboostGrowth90d > 0.05 ? 'bg-emerald-500/90 text-white' : 'bg-black/60 text-[#94a3b8]'
                      }`}>
                        {a.xgboostGrowth90d >= 0 ? '+' : ''}{(a.xgboostGrowth90d * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <div className="flex flex-col gap-1 p-3">
                    <p className="truncate text-sm font-semibold text-[#f1f5f9]">{a.name}</p>
                    <p className="text-xs text-[#64748b]">{fmt(a.spMonthlyListeners)} listeners</p>
                    <div className="flex items-center justify-between">
                      <GrowthBadge v={a.xgboostGrowth90d} />
                      {a.verdict && (
                        <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-medium ${VERDICT_COLORS[a.verdict] ?? ''}`}>
                          {a.verdict}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {!selectedGenre && !sceneLoading && genres.length > 0 && (
        <div className="mt-16 text-center">
          <p className="text-sm text-[#64748b]">Select a genre above to browse artists</p>
        </div>
      )}
    </div>
  )
}
