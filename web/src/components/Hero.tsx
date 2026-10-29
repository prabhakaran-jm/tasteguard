type Preset = {
  id: string
  label: string
  kind?: string
  blurb?: string
  city?: string
}

export type CustomSeed = {
  query: string
  type: 'artist' | 'movie' | 'book' | 'brand'
}

export type CustomListPayload = {
  raw: string
  city: 'Lisbon' | 'New York'
  seeds: CustomSeed[]
}

type Props = {
  presets: Preset[]
  presetId: string
  onPresetChange: (id: string) => void
  onRecorded: () => void
  onLive: () => void
  onCustomList: (payload: CustomListPayload) => void
  running: boolean
  customDraft: string
  onCustomDraftChange: (value: string) => void
  customCity: 'Lisbon' | 'New York'
  onCustomCityChange: (city: 'Lisbon' | 'New York') => void
  customSeeds: CustomSeed[]
  onCustomSeedChange: (index: number, seed: CustomSeed) => void
  blurb?: string
}

const SEED_TYPES: CustomSeed['type'][] = ['artist', 'movie', 'book', 'brand']

export function Hero({
  presets,
  presetId,
  onPresetChange,
  onRecorded,
  onLive,
  onCustomList,
  running,
  customDraft,
  onCustomDraftChange,
  customCity,
  onCustomCityChange,
  customSeeds,
  onCustomSeedChange,
  blurb,
}: Props) {
  const selected = presets.find((p) => p.id === presetId)
  const isRecorded = selected?.kind === 'recorded'

  return (
    <header className="hero">
      <div className="hero-gradient" aria-hidden="true" />
      <div className="hero-inner">
        <div className="hero-lead">
          <h1 className="brand">TasteGuard</h1>
          <p className="promise">
            A cultural firewall for place agents — Qloo knows a Radiohead fan&apos;s
            taste in restaurants, not just music. Verify place + taste, then repair
            from a closed dinner pool.
          </p>
          <p className="guide-line">
            Recommended: select <strong>Radiohead · Lisbon dinner (live)</strong> →
            Run live (taste fails + repair). Then play the recorded stress test for
            the Paris / Cascais catch. Or paste any agent&apos;s list with your
            own taste seeds.
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

        <div className="custom-list-panel">
          <p className="custom-list-label">
            Try your own agent list — pick Lisbon or New York, paste places, and
            optionally add up to 3 taste seeds (leave blank for Radiohead
            seeds in that city).
          </p>
          <div className="custom-city-row" role="group" aria-label="City for pasted list">
            {(['Lisbon', 'New York'] as const).map((city) => (
              <button
                key={city}
                type="button"
                className={
                  customCity === city
                    ? 'cta cta-secondary custom-city-active'
                    : 'cta cta-secondary'
                }
                disabled={running}
                onClick={() => onCustomCityChange(city)}
              >
                {city}
              </button>
            ))}
          </div>
          <div className="custom-seed-grid">
            {customSeeds.map((seed, index) => (
              <div className="custom-seed-row" key={index}>
                <select
                  aria-label={`Seed ${index + 1} type`}
                  value={seed.type}
                  disabled={running}
                  onChange={(e) =>
                    onCustomSeedChange(index, {
                      ...seed,
                      type: e.target.value as CustomSeed['type'],
                    })
                  }
                >
                  {SEED_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  aria-label={`Seed ${index + 1} name`}
                  placeholder={
                    index === 0
                      ? 'e.g. Radiohead'
                      : index === 1
                        ? 'e.g. There Will Be Blood'
                        : 'e.g. Aesop'
                  }
                  value={seed.query}
                  disabled={running}
                  maxLength={80}
                  onChange={(e) =>
                    onCustomSeedChange(index, { ...seed, query: e.target.value })
                  }
                />
              </div>
            ))}
          </div>
          <label className="custom-list-label" htmlFor="custom-agent-list">
            Places in {customCity} (one per line; optional{' '}
            <code>Name | neighbourhood</code>)
          </label>
          <textarea
            id="custom-agent-list"
            className="custom-list-input"
            rows={4}
            value={customDraft}
            onChange={(e) => onCustomDraftChange(e.target.value)}
            disabled={running}
            placeholder={
              customCity === 'New York'
                ? `Peter Luger Steak House | Brooklyn\nHAGS | East Village\n…`
                : `A Cevicheria | Príncipe Real\nCervejaria Ramiro\n…`
            }
          />
          <button
            className="cta cta-secondary"
            type="button"
            disabled={running || !customDraft.trim()}
            onClick={() =>
              onCustomList({
                raw: customDraft,
                city: customCity,
                seeds: customSeeds,
              })
            }
          >
            {running ? 'Running…' : 'Evaluate pasted list'}
          </button>
          <p className="custom-list-hint">
            Always runs live Qloo evaluate → repair. Empty seed fields fall back
            to Radiohead taste seeds for the selected city.
          </p>
        </div>
      </div>
    </header>
  )
}
