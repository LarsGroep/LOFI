"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { Search } from "lucide-react"

export function GlobalSearch() {
  const router = useRouter()
  const [value, setValue] = useState("")
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function navigate(query: string) {
    const q = query.trim()
    if (q) {
      router.push(`/dashboard?q=${encodeURIComponent(q)}`)
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const next = e.target.value
    setValue(next)

    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      navigate(next)
    }, 300)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      navigate(value)
    } else if (e.key === "Escape") {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      setValue("")
    }
  }

  // Clean up debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  return (
    <div className="relative w-full max-w-md">
      <Search
        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[#64748b]"
        aria-hidden="true"
      />
      <input
        type="search"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="Search artists, genres, scenes..."
        aria-label="Search"
        className="h-9 w-full rounded-md border border-[#1e2535] bg-[#161b27] pl-9 pr-3 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:border-[#6366f1] focus:outline-none focus:ring-1 focus:ring-[#6366f1]"
      />
    </div>
  )
}
