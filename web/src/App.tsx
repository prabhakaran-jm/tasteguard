import { useEffect, useState } from 'react'
import { Hero } from './components/Hero'
import { StageCards } from './components/StageCards'
import { StatusCard, kindFromEvaluation } from './components/StatusCard'

type Preset = { id: string; label: string; city: string; persona: string }

type Candidate = {
  name: string
  neighbourhood?: string | null
  address?: string | null
  notes?: string | null
}

type EvaluationResult = {
  evaluation_status: string
  policy_verdict: string | null
  city: string
  candidates: Array<{
    input: Candidate
    evidence: string
    item_verdict: string
    matched_name?: string | null
    distance_km?: number | null
    affinity?: number | null
    anchor_percentile?: number | null
    explainability_summary?: string | null
  }>
  message?: string | null
  anchor_count?: number
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      /* keep statusText */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export default function App() {
  const [presets, setPresets] = useState<Preset[]>([])
  const [presetId, setPresetId] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<string>('live')

  const [proposed, setProposed] = useState<Candidate[] | null>(null)
  const [evalResult, setEvalResult] = useState<EvaluationResult | null>(null)
  const [repairFinal, setRepairFinal] = useState<EvaluationResult | null>(null)
  const [repairHistoryLen, setRepairHistoryLen] = useState(0)

  useEffect(() => {
    api<{ presets: Preset[]; mode: string }>('/api/presets')
      .then((data) => {
        setPresets(data.presets)
        setMode(data.mode)
        if (data.presets[0]) setPresetId(data.presets[0].id)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  async function runDemo() {
    setRunning(true)
    setError(null)
    setProposed(null)
    setEvalResult(null)
    setRepairFinal(null)
    setRepairHistoryLen(0)

    try {
      const propose = await api<{
        mode: string
        candidates: Candidate[]
      }>('/api/propose', {
        method: 'POST',
        body: JSON.stringify({ preset_id: presetId }),
      })
      setMode(propose.mode)
      setProposed(propose.candidates)

      const evaluated = await api<{
        mode: string
        evaluation_id: string
        result: EvaluationResult
      }>('/api/evaluate', {
        method: 'POST',
        body: JSON.stringify({
          preset_id: presetId,
          candidates: propose.candidates,
        }),
      })
      setMode(evaluated.mode)
      setEvalResult(evaluated.result)

      if (
        evaluated.result.evaluation_status === 'completed' &&
        evaluated.result.policy_verdict === 'FAIL'
      ) {
        const repaired = await api<{
          mode: string
          final: EvaluationResult
          history: EvaluationResult[]
        }>('/api/repair', {
          method: 'POST',
          body: JSON.stringify({ evaluation_id: evaluated.evaluation_id }),
        })
        setMode(repaired.mode)
        setRepairFinal(repaired.final)
        setRepairHistoryLen(repaired.history.length)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setRunning(false)
    }
  }

  const showDemo = proposed || evalResult || repairFinal || error

  return (
    <>
      <Hero
        presets={presets}
        presetId={presetId}
        onPresetChange={setPresetId}
        onRun={runDemo}
        running={running}
      />

      {showDemo ? (
        <main className="demo">
          {error ? (
            <StatusCard
              kind="error"
              title="Error"
              body={error}
              mode={mode}
            />
          ) : null}

          {proposed ? (
            <StageCards stageLabel="Stage 1 · Unguarded Gemini" places={proposed} />
          ) : null}

          {evalResult ? (
            <>
              <StatusCard
                kind={kindFromEvaluation(
                  evalResult.evaluation_status,
                  evalResult.policy_verdict,
                )}
                title={
                  evalResult.evaluation_status === 'completed'
                    ? evalResult.policy_verdict || 'FAIL'
                    : evalResult.evaluation_status.toUpperCase()
                }
                body={
                  evalResult.message ||
                  `${evalResult.city} · ${evalResult.anchor_count ?? 0} anchors · ${evalResult.evaluation_status}`
                }
                mode={mode}
              />
              <StageCards
                stageLabel="Stage 2 · TasteGuard verdict"
                scored={evalResult.candidates}
              />
            </>
          ) : null}

          {repairFinal ? (
            <div className="repair-strip">
              <h3>Stage 3 · Closed-set repair</h3>
              <p className="history-note">
                History length {repairHistoryLen} (unguarded snapshot + repair rounds)
              </p>
              <StatusCard
                kind={kindFromEvaluation(
                  repairFinal.evaluation_status,
                  repairFinal.policy_verdict,
                )}
                title={
                  repairFinal.evaluation_status === 'completed'
                    ? repairFinal.policy_verdict || 'FAIL'
                    : repairFinal.evaluation_status.toUpperCase()
                }
                body={
                  repairFinal.message ||
                  `Repaired card · ${repairFinal.evaluation_status}`
                }
                mode={mode}
              />
              <StageCards
                stageLabel="Guarded recommendations"
                scored={repairFinal.candidates}
              />
            </div>
          ) : null}
        </main>
      ) : null}
    </>
  )
}
