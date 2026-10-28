type Kind = 'pass' | 'fail' | 'unavailable' | 'partial' | 'error'

type Props = {
  kind: Kind
  title: string
  body: string
  mode?: string
}

export function StatusCard({ kind, title, body, mode }: Props) {
  return (
    <div className={`status-card ${kind}`} role="status">
      <h2 className="status-title">{title}</h2>
      <p className="status-body">{body}</p>
      {mode ? <span className="mode-tag">mode · {mode}</span> : null}
    </div>
  )
}

export function kindFromEvaluation(
  evaluationStatus: string | undefined,
  policyVerdict: string | null | undefined,
): Kind {
  if (evaluationStatus === 'unavailable') return 'unavailable'
  if (evaluationStatus === 'partial') return 'partial'
  if (policyVerdict === 'PASS') return 'pass'
  if (policyVerdict === 'FAIL') return 'fail'
  return 'fail'
}
