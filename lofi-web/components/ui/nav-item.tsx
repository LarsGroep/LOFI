'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface NavItemProps {
  href: string
  label: string
  icon: LucideIcon
  /** Close the mobile drawer when a link is tapped */
  onNavigate?: () => void
}

export function NavItem({ href, label, icon: Icon, onNavigate }: NavItemProps) {
  const pathname = usePathname()
  const isActive = pathname === href || pathname.startsWith(`${href}/`)

  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={isActive ? 'page' : undefined}
      className={cn(
        'group relative flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors',
        // left active border (always reserve space so labels stay aligned)
        'border-l-2',
        isActive
          ? 'border-[#6366f1] bg-[#1e2535] text-[#6366f1]'
          : 'border-transparent text-[#94a3b8] hover:bg-[#1e2535]/60 hover:text-[#f1f5f9]',
      )}
    >
      <Icon
        className={cn(
          'size-5 shrink-0 transition-colors',
          isActive
            ? 'text-[#6366f1]'
            : 'text-[#94a3b8] group-hover:text-[#f1f5f9]',
        )}
        aria-hidden="true"
      />
      <span className="truncate">{label}</span>
    </Link>
  )
}
