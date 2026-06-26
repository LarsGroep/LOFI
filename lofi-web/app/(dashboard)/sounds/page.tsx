"use client"

import { useState, useMemo, useCallback } from "react"
import useSWR from "swr"
import { X, Plus, ChevronDown, Search, Music2 } from "lucide-react"
import type { ArtistListItem } from "@/types/supabase"

const fetcher = (url: string) => fetch(url).then(r => r.json())

const SOUNDS = [
  'Tech-House', 'House', 'Minimal House', 'Left Field House & Techno',
  'Melodic', 'Melodic Commercial', 'Progressive Techno', 'Techno',
  'Afro House', 'UKG', 'Bounce / Hardhouse', 'Disco', 'Hip-Hop',
  'Dub / Reggae', 'Live',
]

const TIERS = ['A+', 'A', 'B', 'Watch'] as const
type Tier = (typeof TIERS)[number]

const BUCKETS = {
  book_now_sellout:    'Book Now (Sell Out)',
  book_now_future:     'Book Now (Future)',
  watch_nl:            'Watch NL',
  watch_international: 'Watch International',
} as const
type BucketKey = keyof typeof BUCKETS

const TIER_STYLES: Record<Tier, string> = {
  'A+': 'bg-yellow-500/20 text-yellow-300 ring-1 ring-yellow-500/40',
  'A':  'bg-indigo-500/20 text-indigo-300 ring-1 ring-indigo-500/40',
  'B':  'bg-slate-600/40 text-slate-300 ring-1 ring-slate-500/30',
  'Watch': 'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30',
}

const BUCKET_COLORS: Record<BucketKey, string> = {
  book_now_sellout:    'border-green-500/30 bg-green-500/5',
  book_now_future:     'border-indigo-500/30 bg-indigo-500/5',
  watch_nl:            'border-amber-500/30 bg-amber-500/5',
  watch_international: 'border-slate-500/30 bg-slate-500/5',
}

const BUCKET_HEADER: Record<BucketKey, string> = {
  book_now_sellout:    'text-green-400',
  book_now_future:     'text-indigo-400',
  watch_nl:            'text-amber-400',
  watch_international: 'text-slate-400',
}

interface FrameworkEntry {
  id: string
  sound: string
  tier: Tier
  bucket: BucketKey
  added_by: string | null
  notes: string | null
  created_at: string
  artists: {
    id: string
    name: string
    slug: string
    candidate_status: string
    artist_chartmetric: { image_url: string | null; genres: string[] | null; sp_monthly_listeners: number | null } | null
  }
}

function ArtistChip({
  entry,
  onRemove,
  onTierChange,
}: {
  entry: FrameworkEntry
  onRemove: (id: string) => void
  onTierChange: (id: string, tier: Tier) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const artist = entry.artists
  const firstLetter = artist?.name?.trim().charAt(0).toUpperCase() || '?'
  const cm = artist?.artist_chartmetric

  return (
    <div className="group flex items-center gap-2 rounded-lg border border-white/5 bg-[#0e1117] p-2 transition-colors hover:border-white/10">
      <div className="size-8 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10">
        {cm?.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={cm.image_url} alt={artist.name} crossOrigin="anonymous" className="size-full object-cover" />
        ) : (
          <div className="flex size-full items-center justify-center bg-gradient-to-br from-indigo-600 to-slate-800 text-xs font-bold text-white/90">
            {firstLetter}
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <a href={`/artist/${artist.id}`} className="block truncate text-xs font-semibold text-[#f1f5f9] hover:text-[#818cf8]">
          {artist.name}
        </a>
        {cm?.sp_monthly_listeners != null && (
          <span className="text-[10px] text-[#64748b]">
            {cm.sp_monthly_listeners >= 1_000_000
              ? `${(cm.sp_monthly_listeners / 1_000_000).toFixed(1)}M`
              : `${Math.round(cm.sp_monthly_listeners / 1_000)}K`} listeners
          </span>
        )}
      </div>
      <div className="relative flex items-center gap-1">
        <button
          type="button"
          onClick={() => setMenuOpen(v => !v)}
          className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${TIER_STYLES[entry.tier]}`}
        >
          {entry.tier}
        </button>
        {menuOpen && (
          <div className="absolute right-6 top-0 z-20 w-20 overflow-hidden rounded-lg border border-white/10 bg-[#1e2535] py-1 shadow-xl">
            {TIERS.map(t => (
              <button
                key={t}
                type="button"
                onClick={() => { onTierChange(entry.id, t); setMenuOpen(false) }}
                className={`block w-full px-2 py-1 text-left text-xs font-medium hover:bg-[#252d3f] ${entry.tier === t ? 'text-[#f1f5f9]' : 'text-[#94a3b8]'}`}
              >
                {t}
              </button>
            ))}
          </div>
        )}
        <button
          type="button"
          onClick={() => onRemove(entry.id)}
          className="opacity-0 group-hover:opacity-100 transition-opacity text-[#64748b] hover:text-red-400"
          aria-label={`Remove ${artist.name}`}
        >
          <X size={12} />
        </button>
      </div>
    </div>
  )
}

function AddArtistModal({
  sound,
  existingIds,
  onAdd,
  onClose,
}: {
  sound: string
  existingIds: Set<string>
  onAdd: (artistId: string, tier: Tier, bucket: BucketKey) => Promise<void>
  onClose: () => void
}) {
  const { data: allArtists } = useSWR<ArtistListItem[]>('/api/artists?limit=500', fetcher)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [tier, setTier] = useState<Tier>('B')
  const [bucket, setBucket] = useState<BucketKey>('watch_nl')
  const [saving, setSaving] = useState(false)

  const filtered = useMemo(() => {
    if (!allArtists) return []
    return allArtists
      .filter(a => !existingIds.has(a.id))
      .filter(a => !query || a.name.toLowerCase().includes(query.toLowerCase()))
      .slice(0, 20)
  }, [allArtists, existingIds, query])

  async function handleAdd() {
    if (!selectedId) return
    setSaving(true)
    await onAdd(selectedId, tier, bucket)
    setSaving(false)
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-[#161b27] p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold text-[#f1f5f9]">Add Artist to {sound}</h3>
          <button type="button" onClick={onClose} className="text-[#64748b] hover:text-[#f1f5f9]">
            <X size={18} />
          </button>
        </div>

        <div className="relative mb-3">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]" />
          <input
            autoFocus
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search artists…"
            className="w-full rounded-lg border border-white/5 bg-[#1e2535] py-2 pl-9 pr-3 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:outline-none focus:ring-2 focus:ring-[#6366f1]/50"
          />
        </div>

        <div className="mb-4 max-h-48 overflow-y-auto rounded-lg border border-white/5">
          {filtered.length === 0 ? (
            <p className="p-3 text-center text-xs text-[#64748b]">
              {allArtists ? 'No results' : 'Loading…'}
            </p>
          ) : (
            filtered.map(a => (
              <button
                key={a.id}
                type="button"
                onClick={() => setSelectedId(a.id)}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-[#1e2535] ${selectedId === a.id ? 'bg-[#6366f1]/20 text-[#818cf8]' : 'text-[#f1f5f9]'}`}
              >
                <div className="size-6 shrink-0 overflow-hidden rounded-full bg-gradient-to-br from-indigo-600 to-slate-800 flex items-center justify-center text-[10px] font-bold text-white">
                  {a.imageUrl
                    ? <img src={a.imageUrl} alt="" crossOrigin="anonymous" className="size-full object-cover" />
                    : a.name.charAt(0).toUpperCase()}
                </div>
                <span className="truncate">{a.name}</span>
                {a.genres?.[0] && <span className="ml-auto shrink-0 text-[10px] text-[#64748b]">{a.genres[0]}</span>}
              </button>
            ))
          )}
        </div>

        <div className="mb-4 grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-[#64748b]">Tier</label>
            <select
              value={tier}
              onChange={e => setTier(e.target.value as Tier)}
              className="w-full rounded-lg border border-white/5 bg-[#1e2535] px-3 py-2 text-sm text-[#f1f5f9] focus:outline-none focus:ring-2 focus:ring-[#6366f1]/50"
            >
              {TIERS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-[#64748b]">Bucket</label>
            <select
              value={bucket}
              onChange={e => setBucket(e.target.value as BucketKey)}
              className="w-full rounded-lg border border-white/5 bg-[#1e2535] px-3 py-2 text-sm text-[#f1f5f9] focus:outline-none focus:ring-2 focus:ring-[#6366f1]/50"
            >
              {(Object.entries(BUCKETS) as [BucketKey, string][]).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="button"
          disabled={!selectedId || saving}
          onClick={handleAdd}
          className="w-full rounded-lg bg-[#6366f1] py-2 text-sm font-medium text-white transition-colors hover:bg-[#818cf8] disabled:opacity-50"
        >
          {saving ? 'Adding…' : 'Add to Framework'}
        </button>
      </div>
    </div>
  )
}

export default function SoundsPage() {
  const { data: entries, mutate } = useSWR<FrameworkEntry[]>('/api/sounds', fetcher, {
    revalidateOnFocus: false,
  })

  const [activeSound, setActiveSound] = useState(SOUNDS[0])
  const [showModal, setShowModal] = useState(false)

  const soundEntries = useMemo(
    () => (entries ?? []).filter(e => e.sound === activeSound),
    [entries, activeSound]
  )

  const existingIds = useMemo(
    () => new Set(soundEntries.map(e => e.artists?.id).filter(Boolean) as string[]),
    [soundEntries]
  )

  const byBucket = useMemo(() => {
    const map: Record<BucketKey, FrameworkEntry[]> = {
      book_now_sellout: [],
      book_now_future: [],
      watch_nl: [],
      watch_international: [],
    }
    for (const e of soundEntries) {
      if (e.bucket in map) map[e.bucket as BucketKey].push(e)
    }
    for (const bucket of Object.keys(map) as BucketKey[]) {
      map[bucket].sort((a, b) => TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier))
    }
    return map
  }, [soundEntries])

  const handleAdd = useCallback(async (artistId: string, tier: Tier, bucket: BucketKey) => {
    await fetch('/api/sounds', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sound: activeSound, artist_id: artistId, tier, bucket }),
    })
    mutate()
  }, [activeSound, mutate])

  const handleRemove = useCallback(async (entryId: string) => {
    mutate(prev => prev?.filter(e => e.id !== entryId), false)
    await fetch(`/api/sounds/${entryId}`, { method: 'DELETE' })
    mutate()
  }, [mutate])

  const handleTierChange = useCallback(async (entryId: string, tier: Tier) => {
    mutate(prev => prev?.map(e => e.id === entryId ? { ...e, tier } : e), false)
    await fetch(`/api/sounds/${entryId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier }),
    })
    mutate()
  }, [mutate])

  const totalInSound = soundEntries.length

  return (
    <div className="flex flex-col gap-6">
      {showModal && (
        <AddArtistModal
          sound={activeSound}
          existingIds={existingIds}
          onAdd={handleAdd}
          onClose={() => setShowModal(false)}
        />
      )}

      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold text-[#f1f5f9]">Sound Frameworks</h1>
          <p className="text-sm text-[#94a3b8]">
            Curate benchmark artists per sound — powers the AI similarity engine
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-[#6366f1] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#818cf8]"
        >
          <Plus size={16} />
          Add Artist
        </button>
      </header>

      {/* Sound selector */}
      <div className="flex flex-wrap gap-2">
        {SOUNDS.map(s => {
          const count = (entries ?? []).filter(e => e.sound === s).length
          return (
            <button
              key={s}
              type="button"
              onClick={() => setActiveSound(s)}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                activeSound === s
                  ? 'bg-[#6366f1] text-white'
                  : 'bg-[#1e2535] text-[#94a3b8] hover:bg-[#252d3f] hover:text-[#f1f5f9]'
              }`}
            >
              {s}
              {count > 0 && (
                <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${activeSound === s ? 'bg-white/20 text-white' : 'bg-[#252d3f] text-[#64748b]'}`}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Tier legend */}
      <div className="flex items-center gap-4 rounded-lg border border-white/5 bg-[#161b27] px-4 py-2.5 text-xs">
        <span className="text-[#64748b] font-medium">Tiers:</span>
        {TIERS.map(t => (
          <span key={t} className={`rounded-full px-2 py-0.5 font-bold ${TIER_STYLES[t]}`}>{t}</span>
        ))}
        <span className="ml-auto text-[#64748b]">{totalInSound} artists in {activeSound}</span>
      </div>

      {/* Bucket columns */}
      {totalInSound === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-white/10 bg-[#161b27] p-16 text-center">
          <Music2 size={32} className="text-[#64748b]" />
          <p className="text-base font-medium text-[#f1f5f9]">No artists in {activeSound} yet</p>
          <p className="text-sm text-[#94a3b8]">Add benchmark artists to train the AI similarity engine for this sound</p>
          <button
            type="button"
            onClick={() => setShowModal(true)}
            className="mt-2 rounded-lg bg-[#6366f1] px-4 py-2 text-sm font-medium text-white hover:bg-[#818cf8]"
          >
            Add First Artist
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
          {(Object.entries(BUCKETS) as [BucketKey, string][]).map(([bucketKey, bucketLabel]) => (
            <div
              key={bucketKey}
              className={`flex flex-col rounded-xl border ${BUCKET_COLORS[bucketKey]} p-4`}
            >
              <div className="mb-3 flex items-center justify-between">
                <h3 className={`text-sm font-semibold ${BUCKET_HEADER[bucketKey]}`}>
                  {bucketLabel}
                </h3>
                <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs font-medium text-[#94a3b8]">
                  {byBucket[bucketKey].length}
                </span>
              </div>
              <div className="flex flex-col gap-2">
                {byBucket[bucketKey].length === 0 ? (
                  <div className="rounded-lg border border-dashed border-white/10 py-6 text-center text-xs text-[#64748b]">
                    No artists yet
                  </div>
                ) : (
                  byBucket[bucketKey].map(entry => (
                    <ArtistChip
                      key={entry.id}
                      entry={entry}
                      onRemove={handleRemove}
                      onTierChange={handleTierChange}
                    />
                  ))
                )}
                <button
                  type="button"
                  onClick={() => setShowModal(true)}
                  className="mt-1 flex items-center justify-center gap-1 rounded-lg border border-dashed border-white/10 py-2 text-xs text-[#64748b] transition-colors hover:border-[#6366f1]/40 hover:text-[#818cf8]"
                >
                  <Plus size={12} /> Add
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
