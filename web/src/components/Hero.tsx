type Props = {
  presets: { id: string; label: string }[]
  presetId: string
  onPresetChange: (id: string) => void
  onRun: () => void
  running: boolean
}

export function Hero({ presets, presetId, onPresetChange, onRun, running }: Props) {
  return (
    <header className="hero">
      <div className="hero-gradient" aria-hidden="true" />
      <div className="hero-inner">
        <h1 className="brand">TasteGuard</h1>
        <p className="promise">
          A cultural firewall for place agents — verify Gemini picks against
          Qloo taste, then repair from a closed restaurant pool.
        </p>
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
          <button className="cta" type="button" onClick={onRun} disabled={running || !presetId}>
            {running ? 'Running…' : 'Run live demo'}
          </button>
        </div>
      </div>
    </header>
  )
}
