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
  reasons?: string[]
}

type Props = {
  stageLabel: string
  places?: Candidate[]
  scored?: Scored[]
  loading?: boolean
  loadingCount?: number
  showExplainability?: boolean
}

function plainEvidence(s: Scored, showExplainability: boolean): string {
  const parts: string[] = []
  if (
    s.matched_name &&
    s.matched_name.toLowerCase() !== s.input.name.toLowerCase()
  ) {
    parts.push(`Matched as “${s.matched_name}”`)
  } else if (s.matched_name) {
    parts.push('Matched in Qloo')
  } else if (s.evidence === 'unknown' || s.evidence === 'no_confident_match') {
    parts.push('No confident Qloo match')
  } else if (s.evidence === 'mismatch') {
    parts.push('Wrong place or wrong city')
  }
  if (s.distance_km != null && !Number.isNaN(s.distance_km)) {
    parts.push(`${s.distance_km.toFixed(1)} km from centre`)
  }
  if (s.affinity != null && !Number.isNaN(s.affinity)) {
    parts.push(`Taste fit ${Math.round(s.affinity * 100)}`)
  }
  if (s.anchor_percentile != null && !Number.isNaN(s.anchor_percentile)) {
    const topPct = Math.max(1, Math.round((1 - s.anchor_percentile) * 100))
    parts.push(`top ${topPct}% vs Lisbon dinner anchors (allow ≥40th percentile)`)
  }
  if (
    showExplainability &&
    s.explainability_summary &&
    s.explainability_summary !== 'Explanation unavailable'
  ) {
    parts.push(s.explainability_summary)
  } else if (s.reasons && s.reasons[0] && s.evidence === 'mismatch') {
    parts.push(s.reasons[0])
  } else if (s.reasons && s.reasons.some((r) => r.includes('no taste score'))) {
    parts.push(s.reasons.find((r) => r.includes('no taste score')) || '')
  }
  return parts.filter(Boolean).join(' · ') || 'Awaiting evidence'
}

function verdictLabel(v: string): string {
  if (v === 'allow') return 'Allow'
  if (v === 'rewrite') return 'Rewrite'
  return 'Unverified'
}

export function StageCards({
  stageLabel,
  places,
  scored,
  loading,
  loadingCount = 5,
  showExplainability = true,
}: Props) {
  return (
    <section className="stage-block">
      <p className="stage-label">{stageLabel}</p>
      <div className="cards">
        {loading
          ? Array.from({ length: loadingCount }).map((_, i) => (
              <article key={`skel-${i}`} className="place-card skeleton">
                <div className="skel-line wide" />
                <div className="skel-line" />
              </article>
            ))
          : null}

        {!loading && scored
          ? scored.map((s, i) => (
              <article key={`${s.input.name}-${i}`} className={`place-card ${s.item_verdict}`}>
                <div className="card-top">
                  <h3 className="place-name">{s.input.name}</h3>
                  <span className={`verdict-chip ${s.item_verdict}`}>
                    {verdictLabel(s.item_verdict)}
                  </span>
                </div>
                <p className="place-meta">{s.input.neighbourhood || '—'}</p>
                <p className="place-evidence">{plainEvidence(s, showExplainability)}</p>
              </article>
            ))
          : null}

        {!loading && !scored
          ? (places || []).map((p, i) => (
              <article key={`${p.name}-${i}`} className="place-card">
                <h3 className="place-name">{p.name}</h3>
                <p className="place-meta">{p.neighbourhood || '—'}</p>
              </article>
            ))
          : null}
      </div>
    </section>
  )
}
