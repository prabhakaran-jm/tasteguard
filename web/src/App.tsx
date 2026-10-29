import { useEffect, useRef, useState } from 'react'
import { Hero } from './components/Hero'
import { StageCards } from './components/StageCards'
import { StatusCard, kindFromEvaluation } from './components/StatusCard'

type Preset = {
  id: string
  label: string
  city: string
  persona: string
  kind?: string
  blurb?: string
  default?: boolean
}

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
    reasons?: string[]
  }>
  message?: string | null
  anchor_count?: number
  notes?: Record<string, unknown>
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

function explanationsMissing(result: EvaluationResult | null): boolean {
  if (!result?.candidates?.length) return false
  return result.candidates.every(
    (c) =>
      !c.explainability_summary ||
      c.explainability_summary === 'Explanation unavailable',
  )
}

export default function App() {
  const [presets, setPresets] = useState<Preset[]>([])
  const [presetId, setPresetId] = useState('')
  const [running, setRunning] = useState(false)
  const [stageBusy, setStageBusy] = useState<'propose' | 'evaluate' | 'repair' | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<string>('live')

  const [proposed, setProposed] = useState<Candidate[] | null>(null)
  const [evalResult, setEvalResult] = useState<EvaluationResult | null>(null)
  const [repairFinal, setRepairFinal] = useState<EvaluationResult | null>(null)
  const [repairHistoryLen, setRepairHistoryLen] = useState(0)

  const demoRef = useRef<HTMLElement | null>(null)
  const selected = presets.find((p) => p.id === presetId)

  useEffect(() => {
    api<{ presets: Preset[]; default_preset_id?: string }>('/api/presets')
      .then((data) => {
        setPresets(data.presets)
        const def =
          data.presets.find((p) => p.default)?.id ||
          data.default_preset_id ||
          data.presets[0]?.id ||
          ''
        setPresetId(def)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  function scrollToDemo() {
    requestAnimationFrame(() => {
      demoRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  async function runPipeline(forceLive: boolean) {
    setRunning(true)
    setError(null)
    setProposed(null)
    setEvalResult(null)
    setRepairFinal(null)
    setRepairHistoryLen(0)
    setStageBusy('propose')
    scrollToDemo()

    try {
      const propose = await api<{
        mode: string
        candidates: Candidate[]
      }>('/api/propose', {
        method: 'POST',
        body: JSON.stringify({ preset_id: presetId, force_live: forceLive }),
      })
      setMode(propose.mode)
      setProposed(propose.candidates)
      setStageBusy('evaluate')
      scrollToDemo()

      const evaluated = await api<{
        mode: string
        evaluation_id: string
        result: EvaluationResult
      }>('/api/evaluate', {
        method: 'POST',
        body: JSON.stringify({
          preset_id: presetId,
          candidates: propose.candidates,
          force_live: forceLive,
        }),
      })
      setMode(evaluated.mode)
      setEvalResult(evaluated.result)

      if (
        evaluated.result.evaluation_status === 'completed' &&
        evaluated.result.policy_verdict === 'FAIL'
      ) {
        setStageBusy('repair')
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
      setStageBusy(null)
      setRunning(false)
    }
  }

  const showDemo = proposed || evalResult || repairFinal || error || stageBusy
  const hidePerCardExplain =
    explanationsMissing(evalResult) && explanationsMissing(repairFinal || evalResult)

  const repairNote =
    (repairFinal?.notes?.replaced as string[] | undefined)?.join('; ') ||
    repairFinal?.message ||
    null

  return (
    <>
      <Hero
        presets={presets}
        presetId={presetId}
        onPresetChange={setPresetId}
        onRecorded={() => runPipeline(false)}
        onLive={() => runPipeline(true)}
        running={running}
      />

      {showDemo ? (
        <main className="demo" ref={demoRef}>
          <p className="run-mode">
            {mode === 'recorded' ? 'Recorded replay' : 'Live run'} ·{' '}
            {selected?.city}
            {stageBusy === 'propose'
              ? ' · Step 1/3 — proposing list…'
              : null}
            {stageBusy === 'evaluate'
              ? ' · Step 2/3 — verifying with Qloo…'
              : null}
            {stageBusy === 'repair'
              ? ' · Step 3/3 — repairing from closed pool…'
              : null}
          </p>
          {selected ? (
            <p className="persona-line">
              <strong>Who this is for:</strong> {selected.persona}
            </p>
          ) : null}

          {error ? (
            <StatusCard kind="error" title="Error" body={error} />
          ) : null}

          {hidePerCardExplain && (evalResult || repairFinal) ? (
            <p className="explain-banner">
              Qloo did not return per-item explainability contributions for this run.
              Cards show taste fit vs {selected?.city || 'city'} reference restaurants
              instead — not invented explanations.
            </p>
          ) : null}

          <div className="compare-row">
            <StageCards
              stageLabel={
                selected?.kind === 'stress' || selected?.kind === 'recorded'
                  ? 'Injected test list (not Gemini)'
                  : 'Gemini Flash, no tools'
              }
              places={proposed || undefined}
              loading={stageBusy === 'propose'}
              city={selected?.city}
            />
            <StageCards
              stageLabel="TasteGuard"
              scored={evalResult?.candidates}
              loading={stageBusy === 'evaluate'}
              loadingCount={proposed?.length || 5}
              showExplainability={!hidePerCardExplain}
              city={evalResult?.city || selected?.city}
              source={mode === 'recorded' ? 'recorded' : 'live_qloo'}
            />
          </div>

          {evalResult ? (
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
                `${evalResult.city} · ${evalResult.anchor_count ?? 0} anchors`
              }
            />
          ) : null}

          {stageBusy === 'repair' ? (
            <StageCards
              stageLabel="Repair in progress"
              loading
              loadingCount={proposed?.length || 5}
            />
          ) : null}

          {repairFinal ? (
            <div className="repair-strip">
              <h3>After repair</h3>
              <p className="history-note">
                {repairNote ||
                  (repairHistoryLen > 1
                    ? `Repaired in ${repairHistoryLen - 1} round${repairHistoryLen - 1 === 1 ? '' : 's'}`
                    : 'No repair needed')}
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
                body={repairFinal.message || 'Guarded recommendations'}
              />
              <StageCards
                stageLabel="Guarded recommendations"
                scored={repairFinal.candidates}
                showExplainability={!hidePerCardExplain}
                city={repairFinal.city || selected?.city}
                source={mode === 'recorded' ? 'recorded' : 'live_qloo'}
              />
            </div>
          ) : null}
        </main>
      ) : null}

      <footer className="site-footer">
        <p>
          <a href="https://github.com/prabhakaran-jm/tasteguard">GitHub</a>
          {' · '}
          How it works: Gemini proposes → Qloo verifies place + taste → closed-set
          repair
          {' · '}
          Powered by Qloo taste graph
        </p>
        <p className="disclaimer">
          Affinity cutoffs are product policy showing agreement with Qloo’s
          benchmark — not an official Qloo recommendation.
        </p>
      </footer>
    </>
  )
}
