"use client"

import { TrendingUp, Radio } from "lucide-react"

export interface ArtistSignal {
  id: string
  name: string
  imageUrl: string | null
  genre: string
  trendScore: number
  forecast90d: number | null
  lofiFitScore: number
  trigger: string
  sparklineData: number[]
}

function MiniSparkline({ data }: { data: number[] }) {
  if (data.length < 2) {
    return <div className="h-10 w-full rounded bg-[#1e2535]" />
  }
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * 100
      const y = 100 - ((v - min) / range) * 100
      return `${x},${y}`
    })
    .join(" ")

  return (
    <div className="relative h-10 w-full">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full">
        <defs>
          <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline
          points={`0,100 ${points} 100,100`}
          fill="url(#sparkFill)"
          stroke="none"
        />
        <polyline
          points={points}
          fill="none"
          stroke="#818cf8"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  )
}

function MomentumRing({ value }: { value: number }) {
  const size = 44
  const stroke = 4
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (Math.max(0, Math.min(100, value)) / 100) * circumference
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#6366f1"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          fill="none"
        />
      </svg>
      <span className="absolute text-xs font-bold text-[#f1f5f9]">{Math.round(value)}</span>
    </div>
  )
}

export function ArtistRadarCard({ signal }: { signal: ArtistSignal }) {
  const firstLetter = signal.name.trim().charAt(0).toUpperCase() || "?"
  const positive = (signal.forecast90d ?? 0) >= 0

  return (
    <a
      href={`/artist/${signal.id}`}
      className="flex w-[400px] shrink-0 flex-col gap-3 rounded-xl border border-white/5 bg-[#161b27] p-4 transition-colors hover:border-[#6366f1]/40 hover:bg-[#1e2535]"
    >
      <div className="flex items-center gap-4">
        {/* Left: image + name */}
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="size-12 shrink-0 overflow-hidden rounded-full ring-2 ring-white/10">
            {signal.imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={signal.imageUrl || "/placeholder.svg"}
                alt={signal.name}
                crossOrigin="anonymous"
                className="size-full object-cover"
              />
            ) : (
              <div className="flex size-full items-center justify-center bg-gradient-to-br from-indigo-600 to-slate-800">
                <span className="text-lg font-bold text-white/90">{firstLetter}</span>
              </div>
            )}
          </div>
          <div className="min-w-0">
            <p className="truncate font-semibold text-[#f1f5f9]">{signal.name}</p>
            <span className="mt-0.5 inline-block rounded-full bg-white/5 px-2 py-0.5 text-xs text-[#94a3b8]">
              {signal.genre}
            </span>
          </div>
        </div>

        {/* Center: sparkline */}
        <div className="hidden w-24 sm:block">
          <MiniSparkline data={signal.sparklineData} />
        </div>

        {/* Right: momentum ring + delta */}
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <MomentumRing value={signal.trendScore} />
          <span
            className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-medium ${
              positive ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"
            }`}
            title="Predicted 90-day Chartmetric CPP growth"
          >
            <TrendingUp size={11} className={positive ? "" : "rotate-180"} aria-hidden="true" />
            {signal.forecast90d == null ? "—" : `${signal.forecast90d >= 0 ? "+" : ""}${signal.forecast90d.toFixed(1)}%`}
          </span>
          <span className="text-[10px] text-[#64748b]">LOFI {Math.round(signal.lofiFitScore)}%</span>
        </div>
      </div>

      {/* Bottom strip: trigger */}
      <div className="flex items-center gap-1.5 rounded-lg bg-[#1e2535] px-3 py-2 text-xs text-[#94a3b8]">
        <Radio size={13} className="shrink-0 text-[#6366f1]" aria-hidden="true" />
        <span className="truncate">{signal.trigger}</span>
      </div>
    </a>
  )
}
