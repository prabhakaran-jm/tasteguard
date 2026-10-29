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

export type ResultSource = 'recorded' | 'live_qloo'

type Props = {
  stageLabel: string
  places?: Candidate[]
  scored?: Scored[]
  loading?: boolean
  loadingCount?: number
  showExplainability?: boolean
  city?: string
  /** Honest provenance on TasteGuard result cards. */
  source?: ResultSource
}

function formatDistance(km: number): string {
  if (km >= 100) {
    return `${Math.round(km).toLocaleString('en-US')} km away`
  }
  return `${km.toFixed(1)} km from centre`
}

function plainEvidence(s: Scored, showExplainability: boolean, city: string): string {
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
    parts.push(formatDistance(s.distance_km))
  }
  if (s.affinity != null && !Number.isNaN(s.affinity)) {
    parts.push(`Taste fit ${Math.round(s.affinity * 100)}`)
  }
  const borderlineReason = s.reasons?.find((r) => /Borderline/i.test(r))
  if (s.anchor_percentile != null && !Number.isNaN(s.anchor_percentile)) {
    const beats = Math.round(s.anchor_percentile * 100)
    if (s.item_verdict === 'allow' && borderlineReason) {
      // Borderline band ALLOW — do not imply the item failed the 40% cutoff.
      parts.push(
        `Better taste match than ${beats}% of ${city} reference restaurants`,
      )
    } else if (s.item_verdict === 'allow') {
      parts.push(
        `Better taste match than ${beats}% of ${city} reference restaurants`,
      )
    } else {
      parts.push(
        `Better taste match than ${beats}% of ${city} reference restaurants (needs 40%)`,
      )
    }
  }
  if (
    showExplainability &&
    s.explainability_summary &&
    s.explainability_summary !== 'Explanation unavailable'
  ) {
    parts.push(s.explainability_summary)
  } else if (s.reasons && s.reasons[0] && s.evidence === 'mismatch') {
    parts.push(s.reasons[0])
  } else if (borderlineReason) {
    parts.push(borderlineReason)
  } else if (s.reasons && s.reasons.some((r) => r.includes('no taste score'))) {
    parts.push(s.reasons.find((r) => r.includes('no taste score')) || '')
  }
  return parts.filter(Boolean).join(' · ') || 'Awaiting evidence'
}

function verdictLabel(v: string, reasons?: string[]): string {
  if (v === 'allow') return 'Allow'
  if (v === 'rewrite') return 'Rewrite'
  if (reasons?.some((r) => /unscored|no taste score/i.test(r))) return 'Unscored'
  return 'Unverified'
}

function sourceLabel(source: ResultSource): string {
  return source === 'recorded' ? 'recorded' : 'live_qloo'
}

export function StageCards({
  stageLabel,
  places,
  scored,
  loading,
  loadingCount = 5,
  showExplainability = true,
  city = 'in-city',
  source,
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
                  <div className="card-chips">
                    {source ? (
                      <span className={`source-chip ${source}`} title="Result provenance">
                        {sourceLabel(source)}
                      </span>
                    ) : null}
                    <span className={`verdict-chip ${s.item_verdict}`}>
                      {verdictLabel(s.item_verdict, s.reasons)}
                    </span>
                  </div>
                </div>
                <p className="place-meta">{s.input.neighbourhood || '—'}</p>
                <p className="place-evidence">
                  {plainEvidence(s, showExplainability, city)}
                </p>
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
