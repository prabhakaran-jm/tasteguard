import { useEffect, useRef, useState } from 'react'
import { Hero, type CustomListPayload, type CustomSeed } from './components/Hero'
import { OutcomeSummary } from './components/OutcomeSummary'
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

const BUSY_HINT =
  'Live demo is busy, try the recorded run (or wait a minute and retry).'

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
    if (res.status === 429) {
      const msg = typeof detail === 'string' ? detail : BUSY_HINT
      throw new Error(msg.includes('recorded') ? msg : BUSY_HINT)
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

function formatRunStamp(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short',
    })
  } catch {
    return iso
  }
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
  const [runFinishedAt, setRunFinishedAt] = useState<string | null>(null)
  const [elapsedSec, setElapsedSec] = useState<number | null>(null)
  const [fixtureCapturedAt, setFixtureCapturedAt] = useState<string | null>(null)
  const [customDraft, setCustomDraft] = useState('')
  const [customMode, setCustomMode] = useState(false)
  const [customCity, setCustomCity] = useState<'Lisbon' | 'New York'>('Lisbon')
  const [customSeeds, setCustomSeeds] = useState<CustomSeed[]>([
    { query: '', type: 'artist' },
    { query: '', type: 'movie' },
    { query: '', type: 'brand' },
  ])
  const [customPersonaNote, setCustomPersonaNote] = useState<string | null>(null)

  const demoRef = useRef<HTMLElement | null>(null)
  const selected = presets.find((p) => p.id === presetId)

  function parseCustomList(raw: string): Candidate[] {
    const out: Candidate[] = []
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const [namePart, neighbourhoodPart] = trimmed.split('|').map((s) => s.trim())
      if (!namePart) continue
      out.push({
        name: namePart.slice(0, 120),
        neighbourhood: neighbourhoodPart ? neighbourhoodPart.slice(0, 80) : null,
      })
      if (out.length >= 8) break
    }
    return out
  }

  function livePresetForCity(city: 'Lisbon' | 'New York'): string {
    return city === 'New York' ? 'radiohead-nyc' : 'radiohead-lisbon'
  }

  function seedQueriesFromUi(seeds: CustomSeed[]): Array<{ query: string; types: string }> | undefined {
    const filled = seeds
      .map((s) => ({ query: s.query.trim(), types: `urn:entity:${s.type}` }))
      .filter((s) => s.query.length > 0)
    return filled.length ? filled : undefined
  }

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

  async function runEvaluateRepair(
    evaluatePresetId: string,
    candidates: Candidate[],
    forceLive: boolean,
    proposeLabelCandidates?: Candidate[],
    seedQueries?: Array<{ query: string; types: string }>,
  ) {
    setStageBusy('evaluate')
    scrollToDemo()
    let repairAttempted = false
    const body: Record<string, unknown> = {
      preset_id: evaluatePresetId,
      candidates,
      force_live: forceLive,
    }
    if (seedQueries?.length) body.seed_queries = seedQueries
    const evaluated = await api<{
      mode: string
      evaluation_id: string
      result: EvaluationResult
      captured_at?: string | null
    }>('/api/evaluate', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    setMode(evaluated.mode)
    setProposed(proposeLabelCandidates || candidates)
    setEvalResult(evaluated.result)
    if (evaluated.captured_at) setFixtureCapturedAt(evaluated.captured_at)

    if (
      evaluated.result.evaluation_status === 'completed' &&
      evaluated.result.policy_verdict === 'FAIL'
    ) {
      repairAttempted = true
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
    return repairAttempted
  }

  async function runPipeline(forceLive: boolean) {
    setRunning(true)
    setError(null)
    setProposed(null)
    setEvalResult(null)
    setRepairFinal(null)
    setRepairHistoryLen(0)
    setRunFinishedAt(null)
    setElapsedSec(null)
    setFixtureCapturedAt(null)
    setCustomMode(false)
    setCustomPersonaNote(null)
    setStageBusy('propose')
    scrollToDemo()
    const started = performance.now()
    let repairAttempted = false

    try {
      const propose = await api<{
        mode: string
        candidates: Candidate[]
        captured_at?: string | null
      }>('/api/propose', {
        method: 'POST',
        body: JSON.stringify({ preset_id: presetId, force_live: forceLive }),
      })
      setMode(propose.mode)
      setProposed(propose.candidates)
      if (propose.captured_at) setFixtureCapturedAt(propose.captured_at)

      repairAttempted = await runEvaluateRepair(
        presetId,
        propose.candidates,
        forceLive,
        propose.candidates,
      )
      setRunFinishedAt(new Date().toISOString())
      setElapsedSec(Math.round((performance.now() - started) / 100) / 10)
    } catch (err) {
      if (repairAttempted) {
        setError('Repair temporarily unavailable. Run again.')
      } else {
        setError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      setStageBusy(null)
      setRunning(false)
    }
  }

  async function runCustomList(payload: CustomListPayload) {
    const candidates = parseCustomList(payload.raw)
    if (!candidates.length) {
      setError('Paste at least one place name (one per line).')
      return
    }
    const evaluatePresetId = livePresetForCity(payload.city)
    const seedQueries = seedQueriesFromUi(payload.seeds)
    setRunning(true)
    setError(null)
    setProposed(candidates)
    setEvalResult(null)
    setRepairFinal(null)
    setRepairHistoryLen(0)
    setRunFinishedAt(null)
    setElapsedSec(null)
    setFixtureCapturedAt(null)
    setCustomMode(true)
    setCustomPersonaNote(
      seedQueries?.length
        ? `Custom taste seeds: ${seedQueries.map((s) => s.query).join(', ')}`
        : `Using ${evaluatePresetId} preset seeds for ${payload.city}`,
    )
    scrollToDemo()
    const started = performance.now()
    let repairAttempted = false
    try {
      repairAttempted = await runEvaluateRepair(
        evaluatePresetId,
        candidates,
        true,
        candidates,
        seedQueries,
      )
      setRunFinishedAt(new Date().toISOString())
      setElapsedSec(Math.round((performance.now() - started) / 100) / 10)
    } catch (err) {
      if (repairAttempted) {
        setError('Repair temporarily unavailable. Run again.')
      } else {
        setError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      setStageBusy(null)
      setRunning(false)
    }
  }

  const showDemo = proposed || evalResult || repairFinal || error || stageBusy
  const hidePerCardExplain =
    explanationsMissing(evalResult) && explanationsMissing(repairFinal || evalResult)
  const displayCity =
    evalResult?.city ||
    repairFinal?.city ||
    (customMode ? customCity : undefined) ||
    selected?.city

  const repairNote =
    (repairFinal?.notes?.replaced as string[] | undefined)?.join('; ') ||
    repairFinal?.message ||
    null

  const anchors =
    repairFinal?.anchor_count ?? evalResult?.anchor_count ?? null
  const provenanceParts: string[] = []
  if (mode === 'recorded') {
    provenanceParts.push('Source: recorded replay')
    if (fixtureCapturedAt) {
      provenanceParts.push(`fixture captured ${fixtureCapturedAt}`)
    }
  } else {
    provenanceParts.push('Source: live Qloo')
    if (anchors != null) provenanceParts.push(`${anchors} anchors`)
    if (elapsedSec != null) provenanceParts.push(`${elapsedSec}s`)
    if (runFinishedAt) {
      provenanceParts.push(`this run ${formatRunStamp(runFinishedAt)}`)
    }
  }

  return (
    <>
      <Hero
        presets={presets}
        presetId={presetId}
        onPresetChange={setPresetId}
        onRecorded={() => runPipeline(false)}
        onLive={() => runPipeline(true)}
        onCustomList={runCustomList}
        running={running}
        customDraft={customDraft}
        onCustomDraftChange={setCustomDraft}
        customCity={customCity}
        onCustomCityChange={setCustomCity}
        customSeeds={customSeeds}
        onCustomSeedChange={(index, seed) =>
          setCustomSeeds((prev) => prev.map((s, i) => (i === index ? seed : s)))
        }
      />

      {showDemo ? (
        <main className="demo" ref={demoRef}>
          <p className="run-mode">
            {mode === 'recorded' ? 'Recorded replay' : 'Live run'} ·{' '}
            {displayCity}
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
          {provenanceParts.length ? (
            <p className="provenance-line">{provenanceParts.join(' · ')}</p>
          ) : null}
          {customPersonaNote || selected ? (
            <p className="persona-line">
              <strong>Who this is for:</strong>{' '}
              {customPersonaNote || selected?.persona}
            </p>
          ) : null}

          {error ? (
            <StatusCard kind="error" title="Error" body={error} />
          ) : null}

          {hidePerCardExplain && (evalResult || repairFinal) ? (
            <p className="explain-banner">
              Qloo did not return per-item explainability contributions for this run.
              Cards show taste fit vs {displayCity || 'city'} reference restaurants
              instead — not invented explanations.
            </p>
          ) : null}

          <div className="compare-row">
            <StageCards
              stageLabel={
                customMode
                  ? 'Pasted agent list'
                  : selected?.kind === 'stress' || selected?.kind === 'recorded'
                    ? 'Injected test list (not Gemini)'
                    : 'Gemini Flash, no tools'
              }
              places={proposed || undefined}
              loading={stageBusy === 'propose'}
              city={displayCity}
            />
            <StageCards
              stageLabel="TasteGuard"
              scored={evalResult?.candidates}
              loading={stageBusy === 'evaluate'}
              loadingCount={proposed?.length || 5}
              showExplainability={!hidePerCardExplain}
              city={displayCity}
              source={mode === 'recorded' ? 'recorded' : 'live_qloo'}
            />
          </div>

          {evalResult ? (
            <div className="original-list-block">
              <h3 className="stage-heading">Original list</h3>
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
            </div>
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
                city={displayCity}
                source={mode === 'recorded' ? 'recorded' : 'live_qloo'}
              />
            </div>
          ) : null}

          {evalResult &&
          !error &&
          stageBusy !== 'repair' &&
          (repairFinal != null ||
            evalResult.policy_verdict !== 'FAIL' ||
            !running) ? (
            <OutcomeSummary
              initial={evalResult}
              final={repairFinal}
              city={displayCity}
            />
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
