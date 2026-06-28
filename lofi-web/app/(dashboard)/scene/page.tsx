'use client'

import { useState } from 'react'
import useSWR from 'swr'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ScatterChart, Scatter, ZAxis,
} from 'recharts'
import { TrendingUp, TrendingDown, Minus, Radio } from 'lucide-react'

interface GenreRow {
  name: string
  artistCount: number
  avgListeners: number
  avgGrowth: number | null
  pctGrowing: number | null
}

const fetcher = (url: string) => fetch(url).then(r => r.json())

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(Math.round(n))
}

function TrendArrow({ value }: { value: number | null }) {
  if (value == null) return <Minus className="size-4 text-[#64748b]" />
  if (value > 2) return <TrendingUp className="size-4 text-emerald-400" />
  if (value < -2) return <TrendingDown className="size-4 text-rose-400" />
  return <Minus className="size-4 text-[#94a3b8]" />
}

type SortKey = 'artistCount' | 'avgListeners' | 'avgGrowth'

export default function ScenePage() {
  const [sort, setSort] = useState<SortKey>('artistCount')
  const [view, setView] = useState<'bar' | 'scatter' | 'table'>('bar')

  const { data, isLoading } = useSWR<{ genres: GenreRow[] }>('/api/scene', fetcher, { revalidateOnFocus: false })

  const genres = data?.genres ?? []

  const sorted = [...genres].sort((a, b) => {
    if (sort === 'avgGrowth') return (b.avgGrowth ?? -99) - (a.avgGrowth ?? -99)
    if (sort === 'avgListeners') return b.avgListeners - a.avgListeners
    return b.artistCount - a.artistCount
  })

  const top12 = sorted.slice(0, 12)

  // For scatter: x = log listeners, y = growth %, size = artist count
  const scatterData = genres
    .filter(g => g.avgGrowth != null)
    .map(g => ({
      name: g.name,
      x: Math.log10(Math.max(1, g.avgListeners)),
      y: (g.avgGrowth ?? 0) * 100,
      z: g.artistCount,
    }))

  // Summary tiles
  const fastestGrowing = [...genres].filter(g => g.avgGrowth != null).sort((a, b) => (b.avgGrowth ?? 0) - (a.avgGrowth ?? 0))[0]
  const largest = [...genres].sort((a, b) => b.avgListeners - a.avgListeners)[0]
  const mostArtists = [...genres].sort((a, b) => b.artistCount - a.artistCount)[0]
  const risingCount = genres.filter(g => (g.avgGrowth ?? 0) > 0).length

  return (
    <div className="mx-auto max-w-7xl">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[#f1f5f9]">Scene Intelligence</h1>
          <p className="mt-1 text-sm text-[#94a3b8]">
            Genre trends across {genres.reduce((s, g) => s + g.artistCount, 0).toLocaleString()} artist–genre assignments
          </p>
        </div>
        <div className="flex gap-1 rounded-lg border border-[#1e2535] bg-[#161b27] p-0.5">
          {(['bar', 'scatter', 'table'] as const).map(v => (
            <button key={v} type="button" onClick={() => setView(v)}
              className={`rounded-md px-3 py-1 text-xs font-medium capitalize transition-colors ${view === v ? 'bg-[#6366f1] text-white' : 'text-[#94a3b8] hover:text-[#f1f5f9]'}`}>
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* Summary tiles */}
      {!isLoading && (
        <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[
            { label: 'Fastest Growing Genre', value: fastestGrowing?.name ?? '—', sub: fastestGrowing?.avgGrowth != null ? `avg ${fastestGrowing.avgGrowth.toFixed(1)}% 90d CPP growth` : '' },
            { label: 'Largest by Listeners', value: largest?.name ?? '—', sub: fmt(largest?.avgListeners) + ' avg listeners' },
            { label: 'Most Artists', value: mostArtists?.name ?? '—', sub: `${mostArtists?.artistCount ?? 0} artists tracked` },
            { label: 'Genres Growing', value: `${risingCount} / ${genres.length}`, sub: 'positive avg 90d XGBoost growth' },
          ].map(t => (
            <div key={t.label} className="rounded-xl border border-[#1e2535] bg-[#161b27] p-4">
              <p className="text-xs text-[#64748b]">{t.label}</p>
              <p className="mt-1 text-xl font-semibold capitalize text-[#f1f5f9]">{t.value}</p>
              {t.sub && <p className="mt-0.5 text-xs text-[#94a3b8]">{t.sub}</p>}
            </div>
          ))}
        </div>
      )}

      {/* Sort bar */}
      <div className="mt-6 flex items-center gap-2">
        <span className="text-xs text-[#64748b]">Sort by:</span>
        {([['artistCount', 'Artist Count'], ['avgListeners', 'Avg Listeners'], ['avgGrowth', '90d Growth']] as const).map(([key, label]) => (
          <button key={key} type="button" onClick={() => setSort(key)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${sort === key ? 'bg-[#6366f1] text-white' : 'border border-[#1e2535] text-[#94a3b8] hover:text-[#f1f5f9]'}`}>
            {label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="mt-6 h-80 animate-pulse rounded-xl bg-[#161b27]" />
      ) : view === 'bar' ? (
        <div className="mt-4 rounded-xl border border-[#1e2535] bg-[#161b27] p-6">
          <h2 className="mb-4 text-sm font-semibold text-[#f1f5f9]">
            Top 12 Genres — {sort === 'artistCount' ? 'by Artist Count' : sort === 'avgListeners' ? 'by Avg Listeners' : 'by 90d Growth'}
          </h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={top12} layout="vertical" margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" horizontal={false} />
                <XAxis type="number" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false}
                  tickFormatter={v => sort === 'avgGrowth' ? `${(v * 100).toFixed(0)}%` : fmt(v)} />
                <YAxis type="category" dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} width={96} />
                <Tooltip
                  contentStyle={{ background: "#1e2535", border: "none", borderRadius: 8, color: "#f1f5f9" }}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(v: any) => [
                    sort === 'avgGrowth' ? `${(v * 100).toFixed(1)}%` : sort === 'avgListeners' ? fmt(v) : v,
                    sort === 'avgGrowth' ? 'Avg 90d Growth' : sort === 'avgListeners' ? 'Avg Listeners' : 'Artists',
                  ]}
                />
                <Bar dataKey={sort} fill="#6366f1" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : view === 'scatter' ? (
        <div className="mt-4 rounded-xl border border-[#1e2535] bg-[#161b27] p-6">
          <h2 className="mb-1 text-sm font-semibold text-[#f1f5f9]">Genre Landscape</h2>
          <p className="mb-4 text-xs text-[#64748b]">X = avg Spotify listeners (log scale) · Y = avg 90d growth % · size = artist count</p>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                <XAxis type="number" dataKey="x" name="Listeners (log)" stroke="#64748b" fontSize={11}
                  tickLine={false} axisLine={false} tickFormatter={v => fmt(Math.pow(10, v))} />
                <YAxis type="number" dataKey="y" name="90d Growth %" stroke="#64748b" fontSize={11}
                  tickLine={false} axisLine={false} tickFormatter={v => `${v.toFixed(0)}%`} />
                <ZAxis dataKey="z" range={[40, 400]} />
                <Tooltip
                  contentStyle={{ background: "#1e2535", border: "none", borderRadius: 8, color: "#f1f5f9" }}
                  cursor={{ strokeDasharray: "3 3" }}
                  content={({ payload }) => {
                    if (!payload?.length) return null
                    const d = payload[0].payload
                    return (
                      <div className="rounded-lg bg-[#1e2535] px-3 py-2 text-xs">
                        <p className="font-semibold capitalize text-[#f1f5f9]">{d.name}</p>
                        <p className="text-[#94a3b8]">Avg listeners: {fmt(Math.pow(10, d.x))}</p>
                        <p className="text-[#94a3b8]">90d growth: {d.y.toFixed(1)}%</p>
                        <p className="text-[#94a3b8]">Artists: {d.z}</p>
                      </div>
                    )
                  }}
                />
                <Scatter data={scatterData} fill="#6366f1" fillOpacity={0.7} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        /* Table view */
        <div className="mt-4 overflow-hidden rounded-xl border border-[#1e2535] bg-[#161b27]">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e2535] text-left text-xs uppercase tracking-wide text-[#64748b]">
                  <th className="px-4 py-3 font-medium">Genre</th>
                  <th className="px-4 py-3 font-medium text-right">Artists</th>
                  <th className="px-4 py-3 font-medium text-right">Avg Listeners</th>
                  <th className="px-4 py-3 font-medium text-right">90d Growth</th>
                  <th className="px-4 py-3 font-medium text-center">Trend</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map(g => (
                  <tr key={g.name} className="border-t border-[#1e2535] hover:bg-[#1e2535]/40">
                    <td className="px-4 py-3 font-medium capitalize text-[#f1f5f9]">{g.name}</td>
                    <td className="px-4 py-3 text-right text-[#94a3b8]">{g.artistCount}</td>
                    <td className="px-4 py-3 text-right text-[#94a3b8]">{fmt(g.avgListeners)}</td>
                    <td className="px-4 py-3 text-right">
                      {g.avgGrowth != null ? (
                        <span className={`font-semibold ${g.avgGrowth > 2 ? 'text-emerald-400' : g.avgGrowth < -2 ? 'text-rose-400' : 'text-[#94a3b8]'}`}>
                          {g.avgGrowth >= 0 ? '+' : ''}{g.avgGrowth.toFixed(1)}%
                        </span>
                      ) : <span className="text-[#64748b]">—</span>}
                    </td>
                    <td className="px-4 py-3 flex justify-center">
                      <TrendArrow value={g.avgGrowth} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Note about data */}
      {!isLoading && (
        <p className="mt-4 flex items-center gap-1.5 text-xs text-[#64748b]">
          <Radio size={12} />
          Genre aggregation from Chartmetric data across all tracked artists. Growth = avg predicted 90-day Spotify listener change from XGBoost model.
        </p>
      )}
    </div>
  )
}
