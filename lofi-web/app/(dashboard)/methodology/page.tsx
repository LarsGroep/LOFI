import { BarChart2, Compass, Target, TrendingUp } from 'lucide-react'

const SIGNALS = [
  {
    title: 'Trend Forecast',
    weight: '40%',
    icon: TrendingUp,
    body: 'The XGBoost model predicts 90-day Chartmetric CPP score growth. CPP is Chartmetric industry presence, so this is not a Spotify listener forecast.',
  },
  {
    title: 'Scene Evidence',
    weight: '35%',
    icon: Compass,
    body: 'This combines confirmed milestones, RA booking history, and NL/Amsterdam presence. It answers whether the artist is showing real scene traction.',
  },
  {
    title: 'LOFI Fit',
    weight: '25%',
    icon: Target,
    body: 'This checks whether the artist fits LOFI taste, sound, geography, and audience. Fit is separate from trend: a fast-growing artist can still be wrong for LOFI.',
  },
]

export default function MethodologyPage() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold text-[#f1f5f9]">LOFI Fit Methodology</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#94a3b8]">
          This page explains how to read the booking scores. The goal is not to make bookers trust a black box; it is to show what evidence supports a recommendation.
        </p>
      </header>

      <section className="rounded-xl bg-[#161b27] p-6">
        <div className="mb-4 flex items-center gap-2">
          <BarChart2 size={18} className="text-indigo-400" />
          <h2 className="text-lg font-semibold text-slate-100">Overall Booking Signal</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {SIGNALS.map(({ title, weight, icon: Icon, body }) => (
            <div key={title} className="rounded-lg bg-[#1e2535] p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Icon size={15} className="text-indigo-400" />
                  <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
                </div>
                <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-400">{weight}</span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate-400">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-xl bg-[#161b27] p-6">
        <h2 className="text-lg font-semibold text-slate-100">How to Interpret LOFI Fit</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="rounded-lg bg-[#1e2535] p-4">
            <h3 className="text-sm font-semibold text-emerald-400">Strong fit</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              The artist matches LOFI sound, electronic scene context, and likely audience. Strong fit does not automatically mean urgent: check trend and scene evidence too.
            </p>
          </div>
          <div className="rounded-lg bg-[#1e2535] p-4">
            <h3 className="text-sm font-semibold text-amber-400">Moderate or low fit</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              There may be partial genre overlap, weak NL relevance, missing data, or a sound that is adjacent but not core. Use booker notes to correct edge cases.
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-xl bg-[#161b27] p-6">
        <h2 className="text-lg font-semibold text-slate-100">What the AI Should Do</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-400">
          The AI memo should translate structured evidence into booker language. It should not secretly invent scores. It uses the CPP forecast, milestones with sources, LOFI sound framework, scene history, and booker notes to explain the recommendation.
        </p>
      </section>
    </div>
  )
}
