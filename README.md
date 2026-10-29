# TasteGuard

**A cultural firewall for place agents** — Qloo knows a Radiohead fan’s taste in
restaurants, not just music. Verify Gemini picks against the
[Qloo](https://qloo.com) taste graph, then repair weak lists from a closed
in-city dinner pool.

**Same restaurant, two tastes:** Prado fails for a Radiohead fan (26th
percentile) and passes for a Kendrick fan (54th).

**Who it’s for:** travel / hospitality concierge agents — one wrong-city or
off-taste booking becomes a bad review. TasteGuard is the check before the
agent answers.

| | |
|---|---|
| **Live demo** | https://tasteguard-342276031814.us-central1.run.app |
| **Source** | https://github.com/prabhakaran-jm/tasteguard |
| **License** | MIT |

> Affinity cutoffs are **product policy** showing agreement with Qloo’s
> benchmark — not an official Qloo recommendation.

## Try it in 2 minutes (judges)

Five presets + custom paste mode. Recommended path:

1. Open the [live demo](https://tasteguard-342276031814.us-central1.run.app)
   (default = **Stress test · Lisbon (recorded)**).
2. **Play recorded run** (~1s) — 6 places: wrong-city ×2, unresolved ×1, Prado
   taste miss (in-city but weak Radiohead fit); closed-set repair to **PASS**.
3. **Taste compare:** **Radiohead · Lisbon** vs **Kendrick · Lisbon** (live) —
   same city, different Qloo graph; watch Prado’s percentile flip.
4. **Your list:** pick **Lisbon** or **New York**, paste place names
   (`Name | neighbourhood`, one per line), optionally add up to 3 taste
   seeds, then **Evaluate pasted list** — always live evaluate → repair
   (blank seeds → Radiohead profile for that city).
5. Optional: NYC live (~30–45s) or live stress (same inject, real Qloo).

## What makes it Qloo-powered

| Qloo surface | What TasteGuard sends | What the judge sees |
|---|---|---|
| `/search` | Candidate names (+ city bias) | Places resolve (or fail) with distance / mismatch |
| `/v2/insights` + `filter.results.entities` | Verified entity IDs vs city restaurant anchors + taste seeds | Per-item affinity / percentile vs local references |
| Insights `feature.explainability` | Same Insights call | “Taste drivers: …” (top seeds) on cards |

Search resolves; Insights scores taste; TasteGuard policy decides ALLOW /
REWRITE / UNKNOWN; Gemini may only pick closed-set pool IDs on repair.

## Observed results (illustrative)

| Run | Observed (counts only) | Notes |
|---|---|---|
| Lisbon stress · recorded · 2026-10-29 | 6 places; 4 caught (wrong city ×2, unresolved ×1, weak taste ×1 Prado), 4 replaced, **PASS in 1 round** | Default demo; no live Qloo calls |
| Lisbon stress · live | Same 6-place inject; timing typically ~15–30s | **Qloo results may change** |

Named venues and affinity scores stay in the live UI / Devpost screenshots —
not republished here (except the Prado Radiohead/Kendrick flip above).

## Limitations

- Qloo verification does **not** mean a place is open right now.
- The ≥40% anchor percentile (±5% borderline band) is **product policy**, not an
  official Qloo recommendation.
- Stress presets use an **injected test list** so catches are reproducible.
- The recorded fixture is private (Qloo hackathon data terms). A fresh clone
  without the local file gets HTTP 503 on the recorded preset; use a live preset.
- Agent tools are available at `/mcp/sse` (evaluate / repair / list presets) —
  not a full travel agent.
- Live HTTP propose / evaluate / repair are rate-limited per client IP (generous;
  recorded path unlimited). MCP evaluate/repair share one bucket (`mcp:all`) and
  the same daily cap. Counters are in-process; Cloud Run is pinned to
  **max_instances=1** so evaluate→repair shares one `eval_cache` (multi-instance
  could 404 on repair) and the per-IP / MCP caps stay exact.

## Privacy

Qloo receives only taste seeds, candidate place names, and the city — never
user identifiers, accounts, or browser cookies.

## What it does

1. **Propose** — Live presets call Gemini (no tools) for a place list. Stress
   presets use an **injected test list** (not Gemini) so wrong-city and invented
   names are reproducible for judges.
2. **Evaluate** — Qloo Search resolves each place (in-city first, distance +
   category gates). Insights scores affinity vs a city-specific restaurant
   anchor set with `feature.explainability`.
3. **Repair** — On FAIL, Gemini may only pick `entity_id`s from a pre-validated
   dinner alternative pool (max 3 rounds). Invalid Gemini picks fall back to
   top-affinity pool items. ALLOW originals are kept; only rewrite/unknown slots
   are replaced. **PASS requires exactly N ALLOW restaurants.**

## Taste policy

An item is **ALLOW** when it beats **≥40%** of the in-city restaurant anchor set
(±5% borderline band). Categories must look like dinner restaurants (not
café-/bar-only). Wrong-city matches become **REWRITE**; unresolved names become
**UNVERIFIED** / unscored. Incomplete repaired lists never PASS.

There is **no** separate absolute affinity floor in the scorer; borderline
ALLOWs are explained on the card when the ±5% band applies.

## Stack

- Python / FastAPI — resolve, score, repair
- FastMCP (`mcp.server.fastmcp`) — agent tools at `/mcp/sse`
- Vite / React — staged propose → evaluate → repair UI
- Gemini — unguarded propose (live) + closed-set repair picks
- Qloo Search + Insights (`feature.explainability`)
- Cloud Run + Terraform + Artifact Registry

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Set QLOO_API_KEY and GEMINI_API_KEY

$env:PYTHONPATH='.'
uvicorn app.main:app --reload --port 8000
```

SPA (dev):

```powershell
cd web
npm install
npm run dev
```

Prod-shaped (API serves `web/dist`):

```powershell
cd web; npm run build; cd ..
$env:PYTHONPATH='.'
uvicorn app.main:app --port 8000
```

CLI:

```powershell
python -m app evaluate -c "Cervejaria Ramiro" -c "The French Laundry" -s artist:Radiohead
python -m app demo -s artist:Radiohead
```

## Deploy (Cloud Run)

```powershell
cd web; npm run build; cd ..
$TAG = Get-Date -Format "yyyyMMdd-HHmmss"
$IMAGE = "us-central1-docker.pkg.dev/tasteguard-qloo-2026/tasteguard/tasteguard:$TAG"
gcloud builds submit --config=cloudbuild.yaml --substitutions=_IMAGE=$IMAGE --project=tasteguard-qloo-2026
cd infra
terraform apply -var="image=$IMAGE"
terraform output service_url
```

Use a **unique image tag** (not `:latest`) so Terraform creates a new revision.
Secrets live in `infra/secrets.auto.tfvars` (gitignored) → Secret Manager.

**Current post-unfreeze revision:** `tasteguard-00016-c2j`  
**Safe rollback (pre-unfreeze freeze):** `tasteguard-00014-qlk`

```powershell
gcloud run services update-traffic tasteguard --region=us-central1 --to-revisions=tasteguard-00014-qlk=100
```

Re-record the private Lisbon stress fixture after inject/category changes:

```powershell
$env:PYTHONPATH='.'
python scripts/rerecord_stress_lisbon.py
# then rebuild image so Cloud Run ships the new recorded/*.json
```

## API (staged)

- `GET /api/health` — unlimited
- `GET /api/presets` — unlimited
- `POST /api/propose` → `POST /api/evaluate` → `POST /api/repair`
  (live paths rate-limited; recorded preset unlimited)

## MCP (agent tool surface)

Thin FastMCP (official `mcp.server.fastmcp`) mounted at **`/mcp`**.

| | |
|---|---|
| **SSE URL** | `https://tasteguard-342276031814.us-central1.run.app/mcp/sse` |
| **Tools** | `tasteguard_list_presets`, `tasteguard_evaluate`, `tasteguard_repair` |

Example Cursor / Claude Desktop remote server entry:

```json
{
  "mcpServers": {
    "tasteguard": {
      "url": "https://tasteguard-342276031814.us-central1.run.app/mcp/sse"
    }
  }
}
```

Tools wrap the same `TasteGuardService` as the HTTP API (Qloo evaluate + closed-set repair).

DNS-rebinding Host checks are off by default so Cloud Run’s `*.run.app` Host works
(otherwise the SDK returns `421 Invalid Host header`). Optional: set
`MCP_ALLOWED_HOSTS` to a comma-separated allowlist to re-enable checks.

The recorded fixture is captured privately from a live Qloo run and is not
distributed in this repo (Qloo hackathon data terms). On a fresh clone the
recorded preset returns 503; live presets work with your own keys.

## License

MIT — see [LICENSE](LICENSE).
