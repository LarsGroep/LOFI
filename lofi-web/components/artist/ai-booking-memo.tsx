"use client"

import {
  Sparkles,
  RefreshCw,
  Check,
  AlertTriangle,
  TrendingUp,
  AlertCircle,
} from "lucide-react"

export interface BookingMemo {
  verdict: "Book Now" | "Strong Watch" | "Monitor" | "Pass"
  verdictReason: string
  summary: string
  signals: {
    label: string
    rating: "Very Strong" | "Strong" | "Moderate" | "Weak" | "Insufficient Data"
    detail: string
  }[]
  opportunities: string[]
  risks: string[]
  comparablePast: string[]
  generatedAt: string
  dataFreshness: "Fresh" | "Stale" | "Partial"
}

interface AIBookingMemoProps {
  memo: BookingMemo | null
  isLoading: boolean
  onRegenerate: () => void
}

const VERDICT_STYLES: Record<BookingMemo["verdict"], string> = {
  "Book Now": "bg-green-500/20 text-green-400",
  "Strong Watch": "bg-[#6366f1]/20 text-[#818cf8]",
  Monitor: "bg-amber-500/20 text-amber-400",
  Pass: "bg-red-500/20 text-red-400",
}

const RATING_DOT: Record<BookingMemo["signals"][number]["rating"], string> = {
  "Very Strong": "bg-green-400",
  Strong: "bg-green-400",
  Moderate: "bg-amber-400",
  Weak: "bg-red-400",
  "Insufficient Data": "bg-slate-500",
}

const FRESHNESS: Record<BookingMemo["dataFreshness"], { dot: string; text: string }> = {
  Fresh: { dot: "bg-green-400", text: "Data fresh as of today" },
  Partial: { dot: "bg-amber-400", text: "Some sources stale (>48h)" },
  Stale: { dot: "bg-red-400", text: "Stale data — treat with caution" },
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
}

function SignalPill({ signal }: { signal: BookingMemo["signals"][number] }) {
  return (
    <div className="group relative flex items-center gap-2 rounded-lg bg-[#1e2535] px-3 py-2">
      <span className={`size-2 shrink-0 rounded-full ${RATING_DOT[signal.rating]}`} />
      <div className="flex flex-col">
        <span className="text-sm font-medium text-[#f1f5f9]">{signal.label}</span>
        <span className="text-xs text-[#94a3b8]">{signal.rating}</span>
      </div>
      {/* Tooltip */}
      <div className="pointer-events-none absolute -top-2 left-1/2 z-20 w-56 -translate-x-1/2 -translate-y-full rounded-lg border border-white/10 bg-[#0e1117] px-3 py-2 text-xs text-[#94a3b8] opacity-0 shadow-xl transition-opacity group-hover:opacity-100">
        {signal.detail}
      </div>
    </div>
  )
}

export default function AIBookingMemo({ memo, isLoading, onRegenerate }: AIBookingMemoProps) {
  // LOADING STATE
  if (isLoading) {
    return (
      <section className="rounded-xl border border-white/5 bg-[#161b27] p-6">
        <div className="mb-4 flex items-center gap-2">
          <Sparkles size={18} className="text-[#6366f1]" />
          <span className="text-sm font-medium text-[#94a3b8]">Generating booking intelligence…</span>
        </div>
        <div className="flex flex-col gap-4">
          <div className="h-20 animate-pulse rounded-lg bg-[#1e2535]" />
          <div className="h-12 animate-pulse rounded-lg bg-[#1e2535]" />
          <div className="grid grid-cols-3 gap-3">
            <div className="h-14 animate-pulse rounded-lg bg-[#1e2535]" />
            <div className="h-14 animate-pulse rounded-lg bg-[#1e2535]" />
            <div className="h-14 animate-pulse rounded-lg bg-[#1e2535]" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="h-24 animate-pulse rounded-lg bg-[#1e2535]" />
            <div className="h-24 animate-pulse rounded-lg bg-[#1e2535]" />
          </div>
        </div>
      </section>
    )
  }

  // ERROR / EMPTY STATE
  if (!memo) {
    return (
      <section className="flex flex-col items-center gap-3 rounded-xl border border-white/5 bg-[#161b27] p-10 text-center">
        <AlertCircle size={28} className="text-red-400" />
        <p className="text-base font-medium text-[#f1f5f9]">Unable to generate assessment</p>
        <p className="text-sm text-[#94a3b8]">Check that data sources are connected and try again.</p>
        <button
          type="button"
          onClick={onRegenerate}
          className="mt-1 inline-flex items-center gap-2 rounded-lg bg-[#6366f1] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#818cf8]"
        >
          <RefreshCw size={15} aria-hidden="true" />
          Retry
        </button>
      </section>
    )
  }

  const freshness = FRESHNESS[memo.dataFreshness]

  return (
    <section className="rounded-xl border border-white/5 bg-[#161b27] p-6">
      {/* TOP BAR */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-[#6366f1]" />
          <h2 className="text-base font-semibold text-[#f1f5f9]">AI Booking Intelligence</h2>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${VERDICT_STYLES[memo.verdict]}`}>
            {memo.verdict}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[#64748b]">Generated {formatTime(memo.generatedAt)}</span>
          <button
            type="button"
            onClick={onRegenerate}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[#1e2535] px-3 py-1.5 text-xs font-medium text-[#f1f5f9] transition-colors hover:bg-[#252d3f]"
          >
            <RefreshCw size={13} aria-hidden="true" />
            Regenerate
          </button>
        </div>
      </div>

      {/* VERDICT REASON */}
      <blockquote className="mt-4 rounded-r-lg border-l-4 border-[#6366f1] bg-[#6366f1]/10 px-4 py-3">
        <p className="text-base italic text-[#f1f5f9] text-pretty">{memo.verdictReason}</p>
      </blockquote>

      {/* SUMMARY */}
      <p className="mt-4 text-sm leading-relaxed text-[#f1f5f9] text-pretty">{memo.summary}</p>

      {/* SIGNAL PILLS */}
      {memo.signals.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-3">
          {memo.signals.map((s) => (
            <SignalPill key={s.label} signal={s} />
          ))}
        </div>
      )}

      {/* OPPORTUNITIES & RISKS */}
      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-lg bg-[#1e2535] p-4">
          <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-[#f1f5f9]">
            <TrendingUp size={15} className="text-green-400" />
            Opportunities
          </h3>
          <ul className="flex flex-col gap-2">
            {memo.opportunities.map((o, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-[#94a3b8]">
                <Check size={14} className="mt-0.5 shrink-0 text-green-400" />
                <span>{o}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg bg-[#1e2535] p-4">
          <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-[#f1f5f9]">
            <AlertTriangle size={15} className="text-orange-400" />
            Risks
          </h3>
          <ul className="flex flex-col gap-2">
            {memo.risks.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-[#94a3b8]">
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-orange-400" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* COMPARABLE ARTISTS */}
      {memo.comparablePast.length > 0 && (
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <span className="text-sm text-[#94a3b8]">Similar trajectory to:</span>
          {memo.comparablePast.map((c) => (
            <span key={c} className="rounded-full bg-[#1e2535] px-2.5 py-1 text-xs font-medium text-[#f1f5f9]">
              {c}
            </span>
          ))}
        </div>
      )}

      {/* FOOTER — DATA FRESHNESS */}
      <div className="mt-6 flex items-center gap-2 border-t border-white/5 pt-4">
        <span className={`size-2 rounded-full ${freshness.dot}`} />
        <span className="text-xs text-[#94a3b8]">{freshness.text}</span>
      </div>
    </section>
  )
}
