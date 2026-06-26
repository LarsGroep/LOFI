'use client'

import { Suspense } from 'react'
import useSWR from 'swr'
import { useRouter, useSearchParams } from 'next/navigation'
import { DashboardView } from '@/components/dashboard/dashboard-view'
import type { ArtistListItem } from '@/types/supabase'

const fetcher = (url: string) => fetch(url).then(r => r.json())

function DashboardInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialSearch = searchParams.get('q') ?? ''
  const { data: artists, isLoading, error } = useSWR<ArtistListItem[]>('/api/artists', fetcher, {
    revalidateOnFocus: false,
  })

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold text-[#f1f5f9]">Dashboard</h1>
          <p className="text-sm text-[#94a3b8]">Artist Intelligence — LOFI Amsterdam</p>
        </header>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-80 animate-pulse rounded-xl bg-[#161b27]" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-red-400">Failed to load artists. Check your Supabase connection.</p>
      </div>
    )
  }

  return (
    <DashboardView
      artists={artists ?? []}
      onArtistClick={(id) => router.push(`/artist/${id}`)}
      initialSearch={initialSearch}
    />
  )
}

export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardInner />
    </Suspense>
  )
}
