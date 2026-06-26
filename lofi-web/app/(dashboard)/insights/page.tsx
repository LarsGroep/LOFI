'use client'

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { BarChart2, TrendingUp, Download, ChevronUp, ChevronDown, RefreshCw } from 'lucide-react'
import type { ArtistListItem } from '@/types/supabase'

const fetcher = (url: string) => fetch(url).then(r => r.json())

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 999_500) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}K`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(Math.round(n))
}

type SortKey = 'xgboostGrowth90d' | 'spMonthlyListeners' | 'lofiFitScore' | 'raEventCount'
type SortDir = 'asc' | 'desc'

const STATUS_OPTS = ['all', 'pending', 'candidate', 'accepted', 'booked'] as const

const VERDICT_COLORS: Record<string, string> = {
  'Book Now': 'bg-green-500/15 text-green-400',
  'Strong Watch': 'bg-indigo-500/15 text-indigo-400',
  'Monitor': 'bg-amber-500/15 text-amber-400',
  'Pass': 'bg-slate-700 text-slate-400',
}

export default function InsightsPage() {
  const router = useRouter()
  const { data, isLoading } = useSWR<ArtistListItem[]>('/api/artists?limit=2000', fetcher, { revalidateOnFocus: false })

  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [sortKey, setSortKey] = useState<SortKey>('xgboostGrowth90d')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [retraining, setRetraining] = useState(false)
  const [retrainResult, setRetrainResult] = useState<{ ok: boolean; runUrl?: string | null; error?: string } | null>(null)

  const artists = data ?? []

  const rows = useMemo(() => {
    let list = statusFilter === 'all' ? artists : artists.filter(a => a.status === statusFilter)
    list = [...list].sort((a, b) => {
      const av = (a[sortKey] as number | null) ?? -Infinity
      const bv = (b[sortKey] as number | null) ?? -Infinity
      return sortDir === 'desc' ? bv - av : av - bv
    })
    return list
  }, [artists, statusFilter, sortKey, sortDir])

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  function downloadCsv() {
    const headers = ['Name', 'Status', 'Genres', 'Listeners', 'XGBoost 90d %', 'LOFI Fit', 'RA Events', 'Verdict']
    const csvRows = rows.map(a => [
      a.name,
      a.status,
      (a.genres ?? []).join('; '),
      a.spMonthlyListeners ?? '',
      a.xgboostGrowth90d != null ? `${a.xgboostGrowth90d.toFixed(1)}%` : '',
      a.lofiFitScore ?? '',
      a.raEventCount ?? '',
      a.verdict ?? '',
    ])
    const csv = [headers, ...csvRows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'lofi-artist-leaderboard.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleRetrain() {
    setRetraining(true)
    setRetrainResult(null)
    try {
      const res = await fetch('/api/admin/retrain', { method: 'POST' })
      const data = await res.json()
      setRetrainResult(data)
    } catch {
      setRetrainResult({ ok: false, error: 'Network error' })
    } finally {
      setRetraining(false)
    }
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ChevronDown className="size-3 text-[#64748b]" />
    return sortDir === 'desc'
      ? <ChevronDown className="size-3 text-[#818cf8]" />
      : <ChevronUp className="size-3 text-[#818cf8]" />
  }

  return (
    <div className="mx-auto max-w-7xl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[#f1f5f9]">Growth Leaderboard</h1>
          <p className="mt-1 text-sm text-[#94a3b8]">
            {rows.length} artists · sorted by {sortKey === 'xgboostGrowth90d' ? 'XGBoost 90d growth' : sortKey}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={downloadCsv}
            className="inline-flex items-center gap-2 rounded-md border border-[#1e2535] bg-[#161b27] px-3 py-2 text-sm text-[#94a3b8] transition hover:text-[#f1f5f9]"
          >
            <Download className="size-4" />
            CSV Export
          </button>
          <button
            type="button"
            onClick={handleRetrain}
            disabled={retraining}
            className="inline-flex items-center gap-2 rounded-md bg-indigo-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-60"
          >
            <RefreshCw className={`size-4 ${retraining ? 'animate-spin' : ''}`} />
            {retraining ? 'Triggering…' : 'Retrain XGBoost'}
          </button>
        </div>
      </div>
      {retrainResult && (
        <div className={`mt-3 rounded-lg px-4 py-2 text-sm ${retrainResult.ok ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
          {retrainResult.ok ? (
            <>
              Workflow triggered.{' '}
              {retrainResult.runUrl && (
                <a href={retrainResult.runUrl} target="_blank" rel="noopener noreferrer"
                  className="underline hover:text-emerald-300">
                  View run on GitHub →
                </a>
              )}
            </>
          ) : (
            retrainResult.error ?? 'Failed to trigger workflow.'
          )}
        </div>
      )}

      {/* Summary tiles */}
      {!isLoading && (
        <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[
            {
              label: 'Top XGBoost pick',
              icon: TrendingUp,
              value: artists.sort((a, b) => (b.xgboostGrowth90d ?? -1) - (a.xgboostGrowth90d ?? -1))[0]?.name ?? '—',
              sub: artists[0]?.xgboostGrowth90d != null
                ? `+${(artists.sort((a, b) => (b.xgboostGrowth90d ?? -1) - (a.xgboostGrowth90d ?? -1))[0].xgboostGrowth90d!).toFixed(1)}% CPP predicted`
                : '',
            },
            {
              label: 'Book Now artists',
              icon: BarChart2,
              value: String(artists.filter(a => a.verdict === 'Book Now').length),
              sub: 'AI verdict',
            },
            {
              label: 'Strong Watch',
              icon: BarChart2,
              value: String(artists.filter(a => a.verdict === 'Strong Watch').length),
              sub: 'AI verdict',
            },
            {
              label: 'Candidates tracked',
              icon: BarChart2,
              value: String(artists.filter(a => ['candidate', 'accepted', 'booked'].includes(a.status)).length),
              sub: 'in pipeline',
            },
          ].map(tile => (
            <div key={tile.label} className="rounded-xl border border-[#1e2535] bg-[#161b27] p-4">
              <p className="text-xs text-[#64748b]">{tile.label}</p>
              <p className="mt-1 text-2xl font-semibold text-[#f1f5f9]">{tile.value}</p>
              {tile.sub && <p className="mt-0.5 text-xs text-[#94a3b8]">{tile.sub}</p>}
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="mt-6 flex gap-2 overflow-x-auto pb-1">
        {STATUS_OPTS.map(s => (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
              statusFilter === s
                ? 'bg-[#6366f1] text-white'
                : 'border border-[#1e2535] bg-[#161b27] text-[#94a3b8] hover:text-[#f1f5f9]'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="mt-4 overflow-hidden rounded-xl border border-[#1e2535] bg-[#161b27]">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e2535] text-left text-xs uppercase tracking-wide text-[#64748b]">
                <th className="px-4 py-3 font-medium">#</th>
                <th className="px-4 py-3 font-medium">Artist</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Genres</th>
                <th
                  className="cursor-pointer px-4 py-3 font-medium"
                  onClick={() => toggleSort('spMonthlyListeners')}
                >
                  <span className="flex items-center gap-1">Listeners <SortIcon col="spMonthlyListeners" /></span>
                </th>
                <th
                  className="cursor-pointer px-4 py-3 font-medium"
                  onClick={() => toggleSort('xgboostGrowth90d')}
                >
                  <span className="flex items-center gap-1">90d Growth <SortIcon col="xgboostGrowth90d" /></span>
                </th>
                <th
                  className="cursor-pointer px-4 py-3 font-medium"
                  onClick={() => toggleSort('lofiFitScore')}
                >
                  <span className="flex items-center gap-1">LOFI Fit <SortIcon col="lofiFitScore" /></span>
                </th>
                <th
                  className="cursor-pointer px-4 py-3 font-medium"
                  onClick={() => toggleSort('raEventCount')}
                >
                  <span className="flex items-center gap-1">RA Events <SortIcon col="raEventCount" /></span>
                </th>
                <th className="px-4 py-3 font-medium">AI Verdict</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 12 }).map((_, i) => (
                  <tr key={i} className="border-t border-[#1e2535]">
                    {Array.from({ length: 9 }).map((__, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 animate-pulse rounded bg-[#1e2535]" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-sm text-[#64748b]">No artists found</td>
                </tr>
              ) : (
                rows.map((a, i) => (
                  <tr
                    key={a.id}
                    onClick={() => router.push(`/artist/${a.id}`)}
                    className="cursor-pointer border-t border-[#1e2535] transition-colors hover:bg-[#1e2535]/50"
                  >
                    <td className="px-4 py-3 text-[#64748b]">{i + 1}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        {a.imageUrl ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={a.imageUrl} alt="" className="size-8 rounded-full object-cover" />
                        ) : (
                          <div className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-indigo-600 to-slate-800 text-xs font-bold text-white">
                            {a.name.charAt(0)}
                          </div>
                        )}
                        <span className="font-medium text-[#f1f5f9]">{a.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-[#1e2535] px-2 py-0.5 text-xs capitalize text-[#94a3b8]">
                        {a.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[#94a3b8] max-w-[140px]">
                      <span className="line-clamp-1">{(a.genres ?? []).slice(0, 2).join(', ') || '—'}</span>
                    </td>
                    <td className="px-4 py-3 text-[#94a3b8]">{fmt(a.spMonthlyListeners)}</td>
                    <td className="px-4 py-3">
                      {a.xgboostGrowth90d != null ? (
                        <span className={`font-semibold ${a.xgboostGrowth90d >= 5 ? 'text-emerald-400' : a.xgboostGrowth90d < 0 ? 'text-rose-400' : 'text-[#94a3b8]'}`}>
                          {a.xgboostGrowth90d >= 0 ? '+' : ''}{a.xgboostGrowth90d.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-[#64748b]">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {a.lofiFitScore != null ? (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[#1e2535]">
                            <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.min(100, a.lofiFitScore)}%` }} />
                          </div>
                          <span className="text-[#94a3b8]">{Math.round(a.lofiFitScore)}</span>
                        </div>
                      ) : (
                        <span className="text-[#64748b]">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-[#94a3b8]">{a.raEventCount ?? '—'}</td>
                    <td className="px-4 py-3">
                      {a.verdict ? (
                        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${VERDICT_COLORS[a.verdict] ?? 'bg-slate-700 text-slate-400'}`}>
                          {a.verdict}
                        </span>
                      ) : (
                        <span className="text-[#64748b] text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
