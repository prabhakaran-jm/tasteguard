type CandidateRow = {
  item_verdict: string
}

type EvalLike = {
  policy_verdict: string | null
  evaluation_status: string
  candidates: CandidateRow[]
  notes?: Record<string, unknown>
} | null

type Props = {
  initial: EvalLike
  final: EvalLike
  city?: string
}

function countVerdict(rows: CandidateRow[] | undefined, verdict: string): number {
  return (rows || []).filter((c) => c.item_verdict === verdict).length
}

export function OutcomeSummary({ initial, final, city }: Props) {
  if (!initial?.candidates?.length) return null

  const total = initial.candidates.length
  const rejected =
    countVerdict(initial.candidates, 'rewrite') +
    countVerdict(initial.candidates, 'unknown')
  const preserved = countVerdict(initial.candidates, 'allow')
  const display = final || initial
  const allowFinal = countVerdict(display.candidates, 'allow')
  const replacedRaw = final?.notes?.replaced
  const replaced = Array.isArray(replacedRaw)
    ? replacedRaw.length
    : Math.max(0, allowFinal - preserved)

  const passed =
    display.evaluation_status === 'completed' &&
    display.policy_verdict === 'PASS' &&
    allowFinal === total &&
    total > 0

  return (
    <section
      className={`outcome-summary ${passed ? 'pass' : 'fail'}`}
      aria-label="Final outcome summary"
    >
      <p className="outcome-kicker">
        Final outcome{city ? ` · ${city}` : ''}
      </p>
      <div className="outcome-stats">
        <div>
          <strong>{rejected}</strong>
          <span>Rejected</span>
        </div>
        <div>
          <strong>{preserved}</strong>
          <span>Preserved</span>
        </div>
        {final ? (
          <div>
            <strong>{replaced}</strong>
            <span>Replaced</span>
          </div>
        ) : null}
        <div>
          <strong>
            {allowFinal}/{total}
          </strong>
          <span>Final ALLOW</span>
        </div>
      </div>
      <p className="outcome-verdict">
        {passed
          ? `PASS — all ${total} recommendations validated`
          : `${display.policy_verdict || display.evaluation_status.toUpperCase()} — ${allowFinal} of ${total} ALLOW`}
      </p>
    </section>
  )
}
