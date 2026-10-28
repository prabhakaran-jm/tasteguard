type Candidate = {
  name: string
  neighbourhood?: string | null
}

type Scored = {
  input: Candidate
  evidence: string
  item_verdict: string
  matched_name?: string | null
  distance_km?: number | null
  affinity?: number | null
  anchor_percentile?: number | null
  explainability_summary?: string | null
}

type Props = {
  stageLabel: string
  places?: Candidate[]
  scored?: Scored[]
}

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

export function StageCards({ stageLabel, places, scored }: Props) {
  return (
    <section>
      <p className="stage-label">{stageLabel}</p>
      <div className="cards">
        {scored
          ? scored.map((s, i) => (
              <article key={`${s.input.name}-${i}`} className={`place-card ${s.item_verdict}`}>
                <h3 className="place-name">{s.input.name}</h3>
                <p className="place-meta">
                  {s.input.neighbourhood || '—'} · {s.evidence}/{s.item_verdict}
                  {s.matched_name ? ` · match ${s.matched_name}` : ''}
                </p>
                <p className="place-evidence">
                  km {fmt(s.distance_km, 1)} · aff {fmt(s.affinity, 3)} · pct{' '}
                  {fmt(s.anchor_percentile, 2)}
                  {s.explainability_summary ? ` · ${s.explainability_summary}` : ''}
                </p>
              </article>
            ))
          : (places || []).map((p, i) => (
              <article key={`${p.name}-${i}`} className="place-card">
                <h3 className="place-name">{p.name}</h3>
                <p className="place-meta">{p.neighbourhood || '—'}</p>
              </article>
            ))}
      </div>
    </section>
  )
}
