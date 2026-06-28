"use client"

import { useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import useSWR from "swr"
import {
  Plus, Trash2, X, Tag, Users, ChevronDown, ChevronRight,
  TrendingUp, TrendingDown, ExternalLink, RefreshCw, Minus,
  DownloadCloud, Clock,
} from "lucide-react"

const fetcher = (url: string) => fetch(url).then(r => r.json())

interface ArtistCm {
  image_url: string | null
  genres: string[] | null
  sp_monthly_listeners: number | null
  ml_features: Record<string, number | null> | null
  cpp_score: number | null
}

interface MonitorMember {
  id: string
  artist_id: string
  notes: string | null
  added_at: string
  artists: {
    id: string
    name: string
    candidate_status: string
    lofi_feel: Record<string, number> | null
    artist_chartmetric: ArtistCm | ArtistCm[] | null
    xgboost_predictions: { predicted_growth_90d: number | null } | { predicted_growth_90d: number | null }[] | null
  } | null
}

interface MonitorGroup {
  id: string
  name: string
  description: string | null
  color: string
  created_at: string
  rescrape_interval_hours: number | null
  last_scraped_at: string | null
  monitor_group_members: MonitorMember[]
}

const GROUP_COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#e879f9', '#06b6d4', '#f97316', '#ef4444']

const STATUS_STYLES: Record<string, string> = {
  pending:   "bg-slate-700 text-slate-300",
  candidate: "bg-indigo-500/20 text-indigo-400",
  accepted:  "bg-cyan-500/20 text-cyan-400",
  booked:    "bg-green-500/20 text-green-400",
  rejected:  "bg-red-500/20 text-red-400",
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

function fmtDate(value: string | null | undefined): string {
  if (!value) return "Never scraped"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "Unknown"
  const diffHours = Math.round((Date.now() - date.getTime()) / 3_600_000)
  if (diffHours < 1) return "Just now"
  if (diffHours < 24) return `${diffHours}h ago`
  return `${Math.round(diffHours / 24)}d ago`
}

function isScrapeDue(group: MonitorGroup): boolean {
  if (!group.rescrape_interval_hours || !group.last_scraped_at) return false
  const last = new Date(group.last_scraped_at).getTime()
  if (Number.isNaN(last)) return false
  return Date.now() - last >= group.rescrape_interval_hours * 3_600_000
}

function signalLabel(v: number): { text: string; color: string } {
  if (v >= 70) return { text: "Strong",   color: "text-emerald-400" }
  if (v >= 50) return { text: "Moderate", color: "text-indigo-400" }
  if (v >= 30) return { text: "Low",      color: "text-amber-400" }
  return              { text: "Weak",     color: "text-slate-500" }
}

function TrendBadge({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <span className="text-xs text-[#64748b]">—</span>
  const pos = pct >= 0
  return (
    <span className={`flex items-center gap-0.5 text-xs font-medium ${pos ? "text-emerald-400" : "text-rose-400"}`}>
      {pos ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
      {pos ? "+" : ""}{pct.toFixed(1)}%
    </span>
  )
}

function ScorePill({ score, label }: { score: number | null | undefined; label: string }) {
  if (score == null) return null
  const sig = signalLabel(score)
  return (
    <span className={`text-[10px] font-medium ${sig.color}`}>
      {label}: {sig.text}
    </span>
  )
}

function CreateGroupModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("")
  const [desc, setDesc] = useState("")
  const [color, setColor] = useState(GROUP_COLORS[0])
  const [saving, setSaving] = useState(false)

  async function handleCreate() {
    if (!name.trim()) return
    setSaving(true)
    try {
      await fetch('/api/monitor-groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), description: desc.trim() || null, color }),
      })
      onCreated()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-2xl border border-[#1e2535] bg-[#161b27] p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-base font-semibold text-[#f1f5f9]">New monitoring group</h3>
          <button type="button" onClick={onClose} className="text-[#64748b] hover:text-[#f1f5f9]"><X size={16} /></button>
        </div>
        <div className="flex flex-col gap-4">
          <div>
            <label className="mb-1.5 block text-xs text-[#94a3b8]">Group name</label>
            <input
              autoFocus
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="e.g. Book for ADE 2025"
              className="w-full rounded-lg bg-[#1e2535] px-3 py-2 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-[#94a3b8]">Description (optional)</label>
            <input
              value={desc}
              onChange={e => setDesc(e.target.value)}
              placeholder="Context for the AI agent…"
              className="w-full rounded-lg bg-[#1e2535] px-3 py-2 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-[#94a3b8]">Color</label>
            <div className="flex gap-2">
              {GROUP_COLORS.map(c => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`size-6 rounded-full transition ${color === c ? 'ring-2 ring-white ring-offset-2 ring-offset-[#161b27]' : ''}`}
                  style={{ background: c }}
                />
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-[#64748b] hover:text-[#f1f5f9]">Cancel</button>
            <button
              type="button"
              onClick={handleCreate}
              disabled={!name.trim() || saving}
              className="rounded-lg bg-indigo-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
            >
              {saving ? 'Creating…' : 'Create group'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function GroupCard({ group, onRefresh }: { group: MonitorGroup; onRefresh: () => void }) {
  const router = useRouter()
  const [expanded, setExpanded] = useState(true)
  const [removing, setRemoving] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [rescraping, setRescraping] = useState(false)
  const [settingInterval, setSettingInterval] = useState(false)
  const [rescrapeMessage, setRescrapeMessage] = useState<string | null>(null)

  async function removeArtist(artistId: string) {
    setRemoving(artistId)
    try {
      await fetch(`/api/monitor-groups/${group.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artist_id: artistId, action: 'remove' }),
      })
      onRefresh()
    } finally {
      setRemoving(null)
    }
  }

  async function deleteGroup() {
    if (!confirm(`Delete group "${group.name}"?`)) return
    await fetch(`/api/monitor-groups/${group.id}`, { method: 'DELETE' })
    onRefresh()
  }

  async function refreshAll() {
    setRefreshing(true)
    try {
      const ids = (group.monitor_group_members ?? []).map(m => m.artist_id)
      await Promise.allSettled(ids.map(id => fetch(`/api/artists/${id}/refresh`, { method: 'POST' })))
      onRefresh()
    } finally {
      setRefreshing(false)
    }
  }

  async function runRescrape() {
    if (members.length === 0) return
    setRescraping(true)
    setRescrapeMessage(null)
    try {
      const res = await fetch(`/api/monitor-groups/${group.id}/rescrape`, { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error ?? 'Rescrape failed')
      setRescrapeMessage(`Updated ${data.updated ?? 0}/${data.total ?? members.length}`)
      onRefresh()
    } catch (err) {
      setRescrapeMessage(err instanceof Error ? err.message : 'Rescrape failed')
    } finally {
      setRescraping(false)
    }
  }

  async function updateInterval(value: string) {
    setSettingInterval(true)
    try {
      await fetch(`/api/monitor-groups/${group.id}/rescrape`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval_hours: value ? Number(value) : null }),
      })
      onRefresh()
    } finally {
      setSettingInterval(false)
    }
  }

  const members = group.monitor_group_members ?? []
  const scrapeDue = isScrapeDue(group)

  return (
    <div className="rounded-xl border border-[#1e2535] bg-[#161b27] overflow-hidden">
      {/* Group header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <button type="button" onClick={() => setExpanded(v => !v)} className="flex flex-1 items-center gap-3 text-left">
          <div className="size-3 shrink-0 rounded-full" style={{ background: group.color }} />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-[#f1f5f9]">{group.name}</p>
            {group.description && (
              <p className="text-xs text-[#64748b] mt-0.5">{group.description}</p>
            )}
          </div>
          <span className="rounded-full bg-[#1e2535] px-2 py-0.5 text-xs text-[#94a3b8]">{members.length}</span>
          {expanded ? <ChevronDown size={14} className="text-[#64748b]" /> : <ChevronRight size={14} className="text-[#64748b]" />}
        </button>
        {members.length > 0 && (
          <>
            <select
              value={group.rescrape_interval_hours ?? ''}
              onChange={e => updateInterval(e.target.value)}
              disabled={settingInterval}
              title="Set scrape interval"
              className="h-7 rounded-md border border-[#1e2535] bg-[#101521] px-2 text-xs text-[#94a3b8] outline-none hover:border-indigo-500/40 disabled:opacity-40"
            >
              <option value="">Manual</option>
              <option value="24">24h</option>
              <option value="72">3d</option>
              <option value="168">7d</option>
            </select>
            <button
              type="button"
              onClick={runRescrape}
              disabled={rescraping}
              title="Scrape latest Chartmetric data for this group"
              className={`shrink-0 transition-colors disabled:opacity-40 ${scrapeDue ? 'text-amber-400 hover:text-amber-300' : 'text-[#64748b] hover:text-cyan-400'}`}
            >
              <DownloadCloud size={14} className={rescraping ? 'animate-pulse' : ''} />
            </button>
            <button
              type="button"
              onClick={refreshAll}
              disabled={refreshing}
              title="Refresh scores for all artists in this group"
              className="shrink-0 text-[#64748b] hover:text-indigo-400 transition-colors disabled:opacity-40"
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
            </button>
          </>
        )}
        <button type="button" onClick={deleteGroup} className="shrink-0 text-[#64748b] hover:text-red-400 transition-colors">
          <Trash2 size={14} />
        </button>
      </div>

      {expanded && (
        <div className="border-t border-[#1e2535]">
          {members.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-[#64748b]">
              No artists yet. Go to an artist profile and add them to this group.
            </p>
          ) : (
            <>
              {/* Column headers */}
              <div className="grid grid-cols-[auto_1fr_auto_auto_auto_auto_auto] items-center gap-3 border-b border-[#1e2535] px-4 py-1.5">
                <div className="w-8" />
                <span className="text-[10px] font-medium uppercase tracking-wide text-[#64748b]">Artist</span>
                <span className="w-20 text-right text-[10px] font-medium uppercase tracking-wide text-[#64748b]">Listeners</span>
                <span className="w-14 text-right text-[10px] font-medium uppercase tracking-wide text-[#64748b]">30d</span>
                <span className="w-20 text-center text-[10px] font-medium uppercase tracking-wide text-[#64748b]">Momentum</span>
                <span className="w-20 text-center text-[10px] font-medium uppercase tracking-wide text-[#64748b]">Growth</span>
                <div className="w-4" />
              </div>
              <div className="divide-y divide-[#1e2535]">
                {members.map(m => {
                  const artist = m.artists
                  if (!artist) return null
                  const cm = Array.isArray(artist.artist_chartmetric) ? artist.artist_chartmetric[0] : artist.artist_chartmetric
                  const xg = Array.isArray(artist.xgboost_predictions) ? artist.xgboost_predictions[0] : artist.xgboost_predictions
                  const lofi = artist.lofi_feel
                  const sp30d = (cm?.ml_features as Record<string, number | null> | null)?.sp_listeners_30d_pct ?? null
                  const xgGrowth = xg?.predicted_growth_90d ?? null

                  // Arrow direction from XGBoost prediction
                  const xgSignal = xgGrowth != null
                    ? xgGrowth > 5 ? 'up' : xgGrowth < -5 ? 'down' : 'flat'
                    : null

                  return (
                    <div key={m.id} className="grid grid-cols-[auto_1fr_auto_auto_auto_auto_auto] items-center gap-3 px-4 py-2.5 hover:bg-[#1e2535]/50 transition-colors">
                      {/* Avatar */}
                      <div className="size-8 shrink-0 overflow-hidden rounded-full bg-[#1e2535]">
                        {cm?.image_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={cm.image_url} alt={artist.name} className="size-full object-cover" crossOrigin="anonymous" />
                        ) : (
                          <div className="flex size-full items-center justify-center text-xs font-bold text-[#818cf8]">
                            {artist.name.charAt(0)}
                          </div>
                        )}
                      </div>

                      {/* Name + genre + status */}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => router.push(`/artist/${artist.id}`)}
                            className="flex items-center gap-1 text-sm font-medium text-[#f1f5f9] hover:text-[#818cf8] transition-colors"
                          >
                            {artist.name}
                            <ExternalLink size={10} className="opacity-40" />
                          </button>
                          <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-medium capitalize ${STATUS_STYLES[artist.candidate_status] ?? STATUS_STYLES.pending}`}>
                            {artist.candidate_status}
                          </span>
                          {/* 90d outlook arrow from XGBoost */}
                          {xgSignal === 'up'   && <TrendingUp  size={12} className="text-emerald-400 shrink-0" />}
                          {xgSignal === 'down' && <TrendingDown size={12} className="text-rose-400 shrink-0"    />}
                          {xgSignal === 'flat' && <Minus        size={12} className="text-slate-500 shrink-0"   />}
                        </div>
                        <p className="text-[10px] text-[#64748b] truncate">
                          {cm?.genres?.slice(0, 2).join(' · ') ?? '—'}
                          {m.notes ? ` · ${m.notes}` : ''}
                        </p>
                      </div>

                      {/* Spotify listeners */}
                      <span className="w-20 text-right text-xs text-[#94a3b8]">{fmt(cm?.sp_monthly_listeners)}</span>

                      {/* 30d Spotify change */}
                      <div className="w-14 flex justify-end">
                        <TrendBadge pct={sp30d} />
                      </div>

                      {/* Momentum score label */}
                      <div className="w-20 flex justify-center">
                        <ScorePill score={lofi?.momentum} label="M" />
                      </div>

                      {/* Growth score label */}
                      <div className="w-20 flex justify-center">
                        <ScorePill score={lofi?.growth} label="G" />
                      </div>

                      {/* Remove button */}
                      <button
                        type="button"
                        disabled={removing === artist.id}
                        onClick={() => removeArtist(artist.id)}
                        className="w-4 shrink-0 text-[#64748b] hover:text-red-400 transition-colors disabled:opacity-40"
                      >
                        <X size={13} />
                      </button>
                    </div>
                  )
                })}
              </div>

              {/* Group footer — legend */}
              <div className="flex items-center gap-4 border-t border-[#1e2535] px-4 py-2">
                <span className="text-[10px] text-[#64748b]">
                  <TrendingUp size={10} className="inline text-emerald-400 mr-0.5" /> 90d XGBoost outlook
                </span>
                <span className="text-[10px] text-[#64748b]">M = Momentum · G = Growth · 30d = Spotify 30-day change</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default function WatchlistPage() {
  const { data: groups, isLoading, error, mutate } = useSWR<MonitorGroup[]>('/api/monitor-groups', fetcher, {
    revalidateOnFocus: false,
    refreshInterval: 0,
  })
  const [showCreate, setShowCreate] = useState(false)

  const refresh = useCallback(() => mutate(), [mutate])

  const totalArtists = (groups ?? []).reduce((sum, g) => sum + g.monitor_group_members.length, 0)

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <header><h1 className="text-2xl font-bold text-[#f1f5f9]">Watchlist</h1></header>
        <div className="h-48 animate-pulse rounded-xl bg-[#161b27]" />
        <div className="h-48 animate-pulse rounded-xl bg-[#161b27]" />
      </div>
    )
  }

  if (error) {
    return <div className="flex items-center justify-center py-20"><p className="text-sm text-red-400">Failed to load watchlist.</p></div>
  }

  return (
    <div className="flex flex-col gap-6">
      {showCreate && <CreateGroupModal onClose={() => setShowCreate(false)} onCreated={refresh} />}

      <header className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-2xl font-bold text-[#f1f5f9]">Watchlist</h1>
            <p className="text-sm text-[#94a3b8]">Custom monitoring groups — used by the AI agent for context</p>
          </div>
          {totalArtists > 0 && (
            <span className="rounded-full bg-[#1e2535] px-2.5 py-1 text-xs font-medium text-[#94a3b8]">
              {totalArtists} artists across {(groups ?? []).length} groups
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="flex shrink-0 items-center gap-2 rounded-lg bg-indigo-500 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-400 transition-colors"
        >
          <Plus size={14} /> New group
        </button>
      </header>

      {/* How this works */}
      <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 px-4 py-3">
        <div className="flex items-start gap-3">
          <Tag size={15} className="mt-0.5 shrink-0 text-indigo-400" />
          <div className="text-xs text-[#94a3b8] leading-relaxed">
            <strong className="text-indigo-300">How monitoring groups work:</strong> Groups bundle artists for the AI booking agent — e.g. &ldquo;Book for ADE&rdquo; or &ldquo;Under Negotiation&rdquo;. Each row shows live 30-day Spotify momentum, score labels, and a 90-day XGBoost trend arrow. Use the <DownloadCloud size={10} className="inline" /> button to scrape fresh Chartmetric data, or <RefreshCw size={10} className="inline" /> to recompute scores from existing data.
          </div>
        </div>
      </div>

      {(groups ?? []).length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-white/10 bg-[#161b27] p-16 text-center">
          <Users size={32} className="text-[#64748b]" />
          <div>
            <p className="text-base font-medium text-[#f1f5f9]">No monitoring groups yet</p>
            <p className="mt-1 text-sm text-[#64748b]">Create a group to start bundling artists for the AI agent</p>
          </div>
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400"
          >
            <Plus size={14} /> Create first group
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {(groups ?? []).map(group => (
            <GroupCard key={group.id} group={group} onRefresh={refresh} />
          ))}
        </div>
      )}
    </div>
  )
}
