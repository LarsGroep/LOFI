import type { LucideIcon } from "lucide-react"
import { Users, Clock, Star, CheckCircle2, CalendarCheck, TrendingUp, AlertTriangle } from "lucide-react"

interface StatTile {
  label: string
  value: number
  icon: LucideIcon
  accent: string
}

export interface DashboardStats {
  total: number
  pending: number
  candidate: number
  accepted: number
  bookedThisMonth: number
  trending: number
  needsAttention: number
}

export function StatsRow({ stats }: { stats: DashboardStats }) {
  const tiles: StatTile[] = [
    { label: "Tracked", value: stats.total, icon: Users, accent: "text-indigo-400" },
    { label: "Pending", value: stats.pending, icon: Clock, accent: "text-slate-400" },
    { label: "Candidate", value: stats.candidate, icon: Star, accent: "text-amber-400" },
    { label: "Accepted", value: stats.accepted, icon: CheckCircle2, accent: "text-cyan-400" },
    { label: "Booked", value: stats.bookedThisMonth, icon: CalendarCheck, accent: "text-green-400" },
    { label: "Trending", value: stats.trending, icon: TrendingUp, accent: "text-purple-400" },
    { label: "No Memo", value: stats.needsAttention, icon: AlertTriangle, accent: "text-rose-400" },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
      {tiles.map((tile) => {
        const Icon = tile.icon
        return (
          <div key={tile.label} className="flex flex-col gap-2 rounded-xl bg-[#161b27] p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#94a3b8]">{tile.label}</span>
              <Icon className={tile.accent} size={16} aria-hidden="true" />
            </div>
            <span className="text-2xl font-bold text-[#f1f5f9]">{tile.value}</span>
          </div>
        )
      })}
    </div>
  )
}
