'use client'

import { useRef, useState } from 'react'
import { Send, Bot } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ArtistChatProps {
  artistId: string
  artistName: string
  artistContext: string
}

const SUGGESTIONS = [
  (name: string) => `Is ${name} a good LOFI booking? Give a reasoned verdict with key signals.`,
  (name: string) => `What's a realistic fee for ${name} based on comparable artists?`,
  (name: string) => `Why is ${name} growing? Explain in plain language.`,
  (name: string) => `Which reference artists or past LOFI bookings is ${name} comparable to?`,
  (name: string) => `What are the main risks or caveats for booking ${name}?`,
  (name: string) => `Write a 3-4 sentence internal team note about ${name}.`,
]

const SUGGESTION_LABELS = [
  'Good booking?',
  'Realistic fee?',
  'Why growing?',
  'Comparable to…',
  'Risks',
  'Team note',
]

export default function ArtistChat({ artistId, artistName, artistContext }: ArtistChatProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return
    const userMsg: Message = { role: 'user', content: text.trim() }
    const updatedMessages = [...messages, userMsg]
    setMessages(updatedMessages)
    setInput('')
    setLoading(true)

    const assistantMsg: Message = { role: 'assistant', content: '' }
    setMessages(prev => [...prev, assistantMsg])

    try {
      const res = await fetch(`/api/artists/${artistId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text.trim(),
          history: updatedMessages.slice(-8).map(m => ({ role: m.role, content: m.content })),
        }),
      })

      if (!res.body) throw new Error('No body')
      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: next[next.length - 1].content + chunk,
          }
          return next
        })
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      }
    } catch {
      setMessages(prev => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', content: 'Sorry, something went wrong. Try again.' }
        return next
      })
    } finally {
      setLoading(false)
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  const displayedMessages = messages.slice(-12)

  return (
    <section className="flex flex-col gap-3 rounded-xl border border-[#1e2535] bg-[#161b27] p-4">
      <div className="flex items-center gap-2">
        <Bot size={16} className="text-indigo-400" />
        <h2 className="text-sm font-semibold text-[#f1f5f9]">Ask AI about {artistName}</h2>
        {artistContext && (
          <span className="ml-auto text-xs text-[#64748b]">{artistContext}</span>
        )}
      </div>

      {/* Message history */}
      {displayedMessages.length > 0 && (
        <div className="flex max-h-80 flex-col gap-2 overflow-y-auto pr-1">
          {displayedMessages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-indigo-500/20 text-[#f1f5f9]'
                    : 'bg-[#1e2535] text-[#cbd5e1]'
                }`}
              >
                {m.content || (
                  <span className="flex gap-1">
                    <span className="animate-bounce">·</span>
                    <span className="animate-bounce" style={{ animationDelay: '0.15s' }}>·</span>
                    <span className="animate-bounce" style={{ animationDelay: '0.3s' }}>·</span>
                  </span>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Suggestion chips — only shown on empty state */}
      {messages.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((fn, i) => (
            <button
              key={i}
              type="button"
              onClick={() => sendMessage(fn(artistName))}
              className="rounded-full border border-[#1e2535] bg-[#0e1117] px-3 py-1.5 text-xs text-[#94a3b8] transition hover:border-indigo-500/40 hover:text-[#f1f5f9]"
            >
              {SUGGESTION_LABELS[i]}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form
        onSubmit={e => { e.preventDefault(); sendMessage(input) }}
        className="flex items-center gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={`Ask anything about ${artistName}…`}
          disabled={loading}
          className="h-9 flex-1 rounded-lg border border-[#1e2535] bg-[#0e1117] px-3 text-sm text-[#f1f5f9] placeholder:text-[#64748b] focus:border-indigo-500 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-indigo-500 text-white transition hover:bg-indigo-400 disabled:opacity-40"
          aria-label="Send"
        >
          <Send size={14} />
        </button>
      </form>
    </section>
  )
}
