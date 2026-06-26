import { Database, Globe, CheckCircle2, AlertCircle } from "lucide-react"

interface DataSourceCardProps {
  name: string
  description: string
  status: "connected" | "configure"
}

function DataSourceCard({ name, description, status }: DataSourceCardProps) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-[#1e2535] bg-[#161b27] p-4">
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-[#f1f5f9]">{name}</span>
        <span className="text-xs text-[#64748b]">{description}</span>
      </div>
      {status === "connected" ? (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-green-500/10 px-2.5 py-1 text-xs font-medium text-green-400">
          <CheckCircle2 size={12} />
          Connected
        </span>
      ) : (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-400">
          <AlertCircle size={12} />
          Configure
        </span>
      )}
    </div>
  )
}

function SectionHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h2 className="text-base font-semibold text-[#f1f5f9]">{title}</h2>
      {description && <p className="text-sm text-[#64748b]">{description}</p>}
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-[#1e2535] py-3 last:border-0">
      <span className="text-sm text-[#94a3b8]">{label}</span>
      <span className="font-mono text-sm text-[#f1f5f9]">{value}</span>
    </div>
  )
}

const DATA_SOURCES: DataSourceCardProps[] = [
  {
    name: "Chartmetric",
    description: "Spotify, Instagram, TikTok, YouTube, SoundCloud, Beatport charts",
    status: "configure",
  },
  {
    name: "Last.fm",
    description: "Listening trends, genre tags, similar artists",
    status: "configure",
  },
  {
    name: "Resident Advisor",
    description: "Events, lineups, attending counts",
    status: "configure",
  },
  {
    name: "Partyflock",
    description: "NL events, lineups, interest counts — Amsterdam demand signal",
    status: "configure",
  },
  {
    name: "YouTube",
    description: "DJ sets, view velocity, channel growth",
    status: "configure",
  },
]

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-[#f1f5f9]">Settings</h1>
        <p className="text-sm text-[#94a3b8]">App configuration and data source management</p>
      </header>

      {/* App info */}
      <section className="flex flex-col gap-4">
        <SectionHeader
          title="App Info"
          description="Current version and environment details"
        />
        <div className="rounded-xl border border-[#1e2535] bg-[#161b27] px-4 divide-y divide-[#1e2535]">
          <InfoRow label="Version" value="v1.0.0" />
          <InfoRow label="DB Schema" value="public (TimescaleDB)" />
          <InfoRow label="Environment" value={process.env.NODE_ENV ?? "production"} />
          <InfoRow label="Region" value="Amsterdam, NL" />
        </div>
      </section>

      {/* Data sources */}
      <section className="flex flex-col gap-4">
        <SectionHeader
          title="Data Sources"
          description="External integrations that feed the artist intelligence pipeline"
        />
        <div className="flex flex-col gap-3">
          {DATA_SOURCES.map((source) => (
            <DataSourceCard key={source.name} {...source} />
          ))}
        </div>
        <p className="text-xs text-[#64748b]">
          API keys and credentials are configured via environment variables. See{" "}
          <span className="font-mono text-[#94a3b8]">.env.example</span> for required keys.
        </p>
      </section>

      {/* Coming soon placeholder */}
      <section className="flex flex-col gap-4">
        <SectionHeader
          title="Preferences"
          description="Framework weights, alert thresholds, and team configuration"
        />
        <div className="flex items-center justify-center rounded-xl border border-dashed border-[#1e2535] bg-[#161b27]/50 p-10">
          <div className="flex flex-col items-center gap-2 text-center">
            <Database size={24} className="text-[#1e2535]" />
            <p className="text-sm font-medium text-[#64748b]">Coming in Phase 2</p>
            <p className="max-w-xs text-xs text-[#4a5568]">
              Sound framework weights, score thresholds, Slack alert configuration, and per-user preferences will be configurable here.
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
