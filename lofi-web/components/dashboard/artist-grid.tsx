"use client"

import { Compass } from "lucide-react"
import ArtistCard from "@/components/artist/artist-card"

type ArtistCardData = Omit<React.ComponentProps<typeof ArtistCard>, "onFavoriteToggle" | "onClick">

interface ArtistGridProps {
  artists: ArtistCardData[]
  onFavoriteToggle: (id: string) => void
  onArtistClick: (id: string) => void
}

export function ArtistGrid({ artists, onFavoriteToggle, onArtistClick }: ArtistGridProps) {
  if (artists.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[#1e2535] py-20 text-center">
        <Compass className="text-[#64748b]" size={40} aria-hidden="true" />
        <p className="text-sm text-[#94a3b8]">No artists match your filters</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {artists.map((artist) => (
        <ArtistCard
          key={artist.id}
          {...artist}
          onFavoriteToggle={onFavoriteToggle}
          onClick={onArtistClick}
        />
      ))}
    </div>
  )
}
