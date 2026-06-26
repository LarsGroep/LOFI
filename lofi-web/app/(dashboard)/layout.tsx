import type { ReactNode } from 'react'
import { Search } from 'lucide-react'
import { Sidebar } from '@/components/ui/sidebar'

export default function DashboardLayout({
  children,
}: {
  children: ReactNode
}) {
  return (
    <div className="flex h-screen overflow-hidden bg-[#0e1117]">
      <Sidebar />

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="flex h-16 shrink-0 items-center gap-4 border-b border-[#1e2535] bg-[#0e1117] px-4 pl-16 md:px-6 md:pl-6">
          <div className="relative w-full max-w-md">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[#64748b]"
              aria-hidden="true"
            />
            <input
              type="search"
              placeholder="Search artists, genres, scenes..."
              aria-label="Search"
              className="h-9 w-full rounded-md border border-[#1e2535] bg-[#161b27] pl-9 pr-3 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:border-[#6366f1] focus:outline-none focus:ring-1 focus:ring-[#6366f1]"
            />
          </div>

          <div className="ml-auto flex items-center gap-3">
            {/* User avatar */}
            <button
              type="button"
              className="flex size-9 items-center justify-center rounded-full bg-[#1e2535] text-sm font-semibold text-[#818cf8] ring-1 ring-[#1e2535] transition hover:ring-[#6366f1]"
              aria-label="User menu"
            >
              LA
            </button>
          </div>
        </header>

        {/* Scrollable content */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  )
}
