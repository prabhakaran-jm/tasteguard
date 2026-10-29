type Preset = {
  id: string
  label: string
  kind?: string
  blurb?: string
}

type Props = {
  presets: Preset[]
  presetId: string
  onPresetChange: (id: string) => void
  onRecorded: () => void
  onLive: () => void
  running: boolean
  blurb?: string
}

export function Hero({
  presets,
  presetId,
  onPresetChange,
  onRecorded,
  onLive,
  running,
  blurb,
}: Props) {
  const selected = presets.find((p) => p.id === presetId)
  const isRecorded = selected?.kind === 'recorded'

  return (
    <header className="hero">
      <div className="hero-gradient" aria-hidden="true" />
      <div className="hero-inner">
        <h1 className="brand">TasteGuard</h1>
        <p className="promise">
          A cultural firewall for place agents — verify Gemini picks against
          Qloo taste, then repair from a closed restaurant pool.
        </p>
        <p className="guide-line">
          Recommended demo: Lisbon stress (recorded) → Play recorded run. Qloo
          Search resolves places; Insights scores taste; TasteGuard policy +
          Gemini closed-set repair.
        </p>
        {blurb || selected?.blurb ? (
          <p className="preset-blurb">{blurb || selected?.blurb}</p>
        ) : null}
        <div className="cta-row">
          <select
            className="preset-select"
            value={presetId}
            onChange={(e) => onPresetChange(e.target.value)}
            disabled={running || presets.length === 0}
            aria-label="Taste preset"
          >
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          {isRecorded ? (
            <button
              className="cta"
              type="button"
              onClick={onRecorded}
              disabled={running || !presetId}
            >
              {running ? 'Running…' : 'Play recorded run'}
            </button>
          ) : null}
          <button
            className={isRecorded ? 'cta cta-secondary' : 'cta'}
            type="button"
            onClick={onLive}
            disabled={running || !presetId}
          >
            {running ? 'Running…' : 'Run live'}
          </button>
        </div>
      </div>
    </header>
  )
}
