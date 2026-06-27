'use client'

import useSWR from 'swr'
import { Database, AlertTriangle, CheckCircle2, Users, BarChart2, Copy, Tag, Zap } from 'lucide-react'

const fetcher = (url: string) => fetch(url).then(r => r.json())

interface DbHealth {
  total: number
  active: number
  excluded: number
  excludedByReason: { reason: string; count: number }[]
  missingChartmetric: number
  missingRA: number
  missingMLFeatures: number
  missingLOFIScore: number
  missingPredictions: number
  missingGenres: number
  byStatus: { status: string; count: number }[]
  duplicateNames: { name: string; count: number }[]
  tableSizes: Record<string, number>
}

function MetricCard({ label, value, icon: Icon, accent, warn }: {
  label: string
  value: number | null
  icon: React.ElementType
  accent: string
  warn?: boolean
}) {
  return (
    <div className={`flex flex-col gap-2 rounded-xl p-4 ${warn && (value ?? 0) > 0 ? 'bg-amber-500/5 border border-amber-500/20' : 'bg-[#161b27]'}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs text-[#94a3b8]">{label}</span>
        <Icon className={accent} size={15} />
      </div>
      <span className={`text-2xl font-bold ${warn && (value ?? 0) > 0 ? 'text-amber-400' : 'text-[#f1f5f9]'}`}>
        {value ?? '—'}
      </span>
    </div>
  )
}

const STATUS_COLORS: Record<string, string> = {
  booked: 'bg-green-500/20 text-green-400',
  accepted: 'bg-cyan-500/20 text-cyan-400',
  candidate: 'bg-indigo-500/20 text-indigo-400',
  pending: 'bg-slate-500/20 text-slate-400',
  rejected: 'bg-rose-500/20 text-rose-400',
}

export default function AdminPage() {
  const { data, isLoading, error, mutate } = useSWR<DbHealth>('/api/admin/db-health', fetcher, {
    revalidateOnFocus: false,
    refreshInterval: 0,
  })

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-[#161b27]" />
        ))}
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-red-400">Failed to load database health.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#f1f5f9]">Database Health</h1>
          <p className="text-sm text-[#94a3b8]">Artist data quality and coverage report</p>
        </div>
        <button
          type="button"
          onClick={() => mutate()}
          className="rounded-lg border border-[#1e2535] bg-[#161b27] px-3 py-1.5 text-xs text-[#94a3b8] transition hover:border-indigo-500/40 hover:text-[#f1f5f9]"
        >
          Refresh
        </button>
      </header>

      {/* Artist counts */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-[#94a3b8]">Artist Population</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard label="Total" value={data.total} icon={Database} accent="text-indigo-400" />
          <MetricCard label="Active" value={data.active} icon={CheckCircle2} accent="text-green-400" />
          <MetricCard label="Excluded" value={data.excluded} icon={AlertTriangle} accent="text-amber-400" warn />
          <MetricCard label="Duplicates" value={data.duplicateNames.length} icon={Copy} accent="text-rose-400" warn />
        </div>
      </section>

      {/* Status breakdown */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-[#94a3b8]">By Status (active artists)</h2>
        <div className="flex flex-wrap gap-2">
          {data.byStatus.map(({ status, count }) => (
            <div key={status} className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${STATUS_COLORS[status] ?? 'bg-slate-500/20 text-slate-400'}`}>
              <span className="font-medium capitalize">{status}</span>
              <span className="font-bold">{count}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Coverage gaps */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-[#94a3b8]">Coverage Gaps (active artists)</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <MetricCard label="Missing Chartmetric" value={data.missingChartmetric} icon={BarChart2} accent="text-slate-400" warn />
          <MetricCard label="Missing RA" value={data.missingRA} icon={Zap} accent="text-slate-400" warn />
          <MetricCard label="Missing ML Features" value={data.missingMLFeatures} icon={BarChart2} accent="text-slate-400" warn />
          <MetricCard label="Missing LOFI Score" value={data.missingLOFIScore} icon={Tag} accent="text-slate-400" warn />
          <MetricCard label="Missing Predictions" value={data.missingPredictions} icon={BarChart2} accent="text-slate-400" warn />
          <MetricCard label="Missing Genres" value={data.missingGenres} icon={Tag} accent="text-slate-400" warn />
        </div>
      </section>

      {/* Table sizes */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-[#94a3b8]">Table Sizes</h2>
        <div className="overflow-hidden rounded-xl border border-[#1e2535]">
          <table className="w-full text-sm">
            <thead className="border-b border-[#1e2535] bg-[#0e1117]">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#64748b]">Table</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#64748b]">Rows</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e2535] bg-[#161b27]">
              {Object.entries(data.tableSizes).map(([table, count]) => (
                <tr key={table}>
                  <td className="px-4 py-2 font-mono text-xs text-[#94a3b8]">{table}</td>
                  <td className="px-4 py-2 text-right font-mono text-xs text-[#f1f5f9]">{count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Exclusion log */}
      {data.excludedByReason.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-[#94a3b8]">Exclusion Log</h2>
          <div className="overflow-hidden rounded-xl border border-[#1e2535]">
            <table className="w-full text-sm">
              <thead className="border-b border-[#1e2535] bg-[#0e1117]">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-[#64748b]">Reason</th>
                  <th className="px-4 py-2.5 text-right text-xs font-medium text-[#64748b]">Count</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e2535] bg-[#161b27]">
                {data.excludedByReason.map(({ reason, count }) => (
                  <tr key={reason}>
                    <td className="px-4 py-2 text-xs text-[#94a3b8]">
                      <span className={`mr-2 inline-block size-1.5 rounded-full align-middle ${reason.startsWith('auto') ? 'bg-rose-400' : 'bg-amber-400'}`} />
                      {reason}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-[#f1f5f9]">{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-[#64748b]">
            <span className="inline-block size-1.5 rounded-full bg-rose-400 align-middle" /> = auto-delete candidate &nbsp;
            <span className="inline-block size-1.5 rounded-full bg-amber-400 align-middle" /> = needs review
          </p>
        </section>
      )}

      {/* Duplicate names */}
      {data.duplicateNames.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-[#94a3b8]">Duplicate Artist Names</h2>
          <div className="flex flex-wrap gap-2">
            {data.duplicateNames.map(({ name, count }) => (
              <span key={name} className="rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-1 text-xs text-rose-400">
                {name} ×{count}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
