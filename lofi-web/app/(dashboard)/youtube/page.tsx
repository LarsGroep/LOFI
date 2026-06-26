'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { PlayCircle, TrendingUp, Search, Play } from 'lucide-react'

interface YoutubeSet {
  video_id: string
  platform: string
  title: string | null
  published_at: string | null
  thumbnail_url: string | null
  matched_artist_names: string[] | null
  detected_artist_names: string[] | null
  view_count: number | null
  like_count: number | null
  view_velocity: number | null
  is_trending: boolean | null
}

const fetcher = (url: string) => fetch(url).then(r => r.json())

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(Math.round(n))
}

export default function YoutubeSetPage() {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'trending'>('all')

  const { data, isLoading } = useSWR<YoutubeSet[]>(
    `/api/youtube?limit=120`,
    fetcher,
    { revalidateOnFocus: false }
  )

  const sets = data ?? []
  const filtered = sets.filter(s => {
    if (filter === 'trending' && !s.is_trending) return false
    if (search) {
      const q = search.toLowerCase()
      return (
        (s.title ?? '').toLowerCase().includes(q) ||
        (s.matched_artist_names ?? []).some(a => a.toLowerCase().includes(q)) ||
        (s.detected_artist_names ?? []).some(a => a.toLowerCase().includes(q))
      )
    }
    return true
  })

  const trendingCount = sets.filter(s => s.is_trending).length

  return (
    <div className="mx-auto max-w-7xl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[#f1f5f9]">YouTube Sets</h1>
          <p className="mt-1 text-sm text-[#94a3b8]">
            {sets.length} sets tracked · {trendingCount} trending
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[#64748b]" />
            <input
              type="search"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search sets or artists…"
              className="h-9 w-56 rounded-md border border-[#1e2535] bg-[#161b27] pl-9 pr-3 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:border-[#6366f1] focus:outline-none"
            />
          </div>
          <div className="flex rounded-lg border border-[#1e2535] bg-[#161b27] p-0.5">
            {(['all', 'trending'] as const).map(f => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={`rounded-md px-3 py-1 text-xs font-medium capitalize transition-colors ${
                  filter === f ? 'bg-[#6366f1] text-white' : 'text-[#94a3b8] hover:text-[#f1f5f9]'
                }`}
              >
                {f === 'trending' ? (
                  <span className="flex items-center gap-1"><TrendingUp className="size-3" />{f}</span>
                ) : f}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="h-56 animate-pulse rounded-xl bg-[#161b27]" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="mt-16 flex flex-col items-center gap-3 text-center">
          <PlayCircle className="size-10 text-[#64748b]" />
          <p className="text-sm text-[#64748b]">No sets found</p>
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map(s => {
            const youtubeUrl = s.platform === 'youtube'
              ? `https://www.youtube.com/watch?v=${s.video_id}`
              : `https://www.youtube.com/watch?v=${s.video_id}`
            return (
              <a
                key={s.video_id}
                href={youtubeUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex flex-col overflow-hidden rounded-xl border border-[#1e2535] bg-[#161b27] transition-all hover:border-[#6366f1]/40 hover:shadow-lg"
              >
                <div className="relative aspect-video w-full overflow-hidden bg-[#0e1117]">
                  {s.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={s.thumbnail_url}
                      alt={s.title ?? ''}
                      className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center">
                      <PlayCircle className="size-10 text-[#1e2535]" />
                    </div>
                  )}
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                    <div className="flex size-12 items-center justify-center rounded-full bg-black/70">
                      <Play className="size-5 fill-white text-white" />
                    </div>
                  </div>
                  {s.is_trending && (
                    <span className="absolute left-2 top-2 flex items-center gap-1 rounded-full bg-indigo-500/90 px-2 py-0.5 text-[10px] font-semibold text-white">
                      <TrendingUp className="size-3" /> Trending
                    </span>
                  )}
                </div>
                <div className="flex flex-1 flex-col gap-1 p-3">
                  <p className="line-clamp-2 text-sm font-medium leading-snug text-[#f1f5f9]">
                    {s.title ?? 'Untitled'}
                  </p>
                  {(s.matched_artist_names ?? []).length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {(s.matched_artist_names ?? []).slice(0, 3).map(a => (
                        <span key={a} className="rounded-full bg-indigo-500/10 px-1.5 py-0.5 text-[10px] text-indigo-300">
                          {a}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="mt-auto flex items-center justify-between pt-2 text-xs text-[#64748b]">
                    <span>{s.published_at ? new Date(s.published_at).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : ''}</span>
                    <span>{fmt(s.view_count)} views</span>
                  </div>
                </div>
              </a>
            )
          })}
        </div>
      )}
    </div>
  )
}
