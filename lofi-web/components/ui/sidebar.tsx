'use client'

import { useState } from 'react'
import {
  LayoutDashboard,
  Compass,
  Star,
  KanbanSquare,
  Music,
  BarChart2,
  Settings,
  Menu,
  X,
  Youtube,
  Radio,
} from 'lucide-react'
import { NavItem } from '@/components/ui/nav-item'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/scout', label: 'Scout', icon: Compass },
  { href: '/watchlist', label: 'Watchlist', icon: Star },
  { href: '/pipeline', label: 'Pipeline', icon: KanbanSquare },
  { href: '/sounds', label: 'Sounds', icon: Music },
  { href: '/insights', label: 'Leaderboard', icon: BarChart2 },
  { href: '/youtube', label: 'YouTube Sets', icon: Youtube },
  { href: '/scene', label: 'Scene Intel', icon: Radio },
  { href: '/settings', label: 'Settings', icon: Settings },
] as const

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      {/* Logo / wordmark */}
      <div className="flex h-16 items-center gap-2 px-5">
        <div className="flex size-8 items-center justify-center rounded-md bg-[#6366f1]">
          <Music className="size-4 text-[#f1f5f9]" aria-hidden="true" />
        </div>
        <span className="text-lg font-bold tracking-tight text-[#f1f5f9]">
          LOFI
          <span className="ml-1 font-medium text-[#94a3b8]">Intelligence</span>
        </span>
      </div>

      {/* Nav */}
      <nav className="flex flex-1 flex-col gap-1 px-3 py-4" aria-label="Primary">
        {NAV_ITEMS.map((item) => (
          <NavItem
            key={item.href}
            href={item.href}
            label={item.label}
            icon={item.icon}
            onNavigate={onNavigate}
          />
        ))}
      </nav>

      {/* Footer slot */}
      <div className="border-t border-[#1e2535] px-5 py-4">
        <p className="text-xs text-[#94a3b8]">LOFI Amsterdam</p>
        <p className="text-xs text-[#64748b]">Artist Scouting v1.0</p>
      </div>
    </div>
  )
}

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <>
      {/* Mobile top trigger */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        className="fixed left-4 top-3.5 z-40 inline-flex size-9 items-center justify-center rounded-md border border-[#1e2535] bg-[#161b27] text-[#f1f5f9] md:hidden"
        aria-label="Open navigation menu"
      >
        <Menu className="size-5" aria-hidden="true" />
      </button>

      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 border-r border-[#1e2535] bg-[#161b27] md:block">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      <div
        className={cn(
          'fixed inset-0 z-50 md:hidden',
          mobileOpen ? 'pointer-events-auto' : 'pointer-events-none',
        )}
        aria-hidden={!mobileOpen}
      >
        {/* Overlay */}
        <div
          onClick={() => setMobileOpen(false)}
          className={cn(
            'absolute inset-0 bg-black/60 transition-opacity',
            mobileOpen ? 'opacity-100' : 'opacity-0',
          )}
        />
        {/* Panel */}
        <div
          className={cn(
            'absolute left-0 top-0 h-full w-60 border-r border-[#1e2535] bg-[#161b27] transition-transform duration-200',
            mobileOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            className="absolute right-3 top-4 inline-flex size-8 items-center justify-center rounded-md text-[#94a3b8] hover:bg-[#1e2535] hover:text-[#f1f5f9]"
            aria-label="Close navigation menu"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
          <SidebarContent onNavigate={() => setMobileOpen(false)} />
        </div>
      </div>
    </>
  )
}
