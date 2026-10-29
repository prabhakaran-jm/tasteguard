# TasteGuard

**A cultural firewall for place agents** — verify Gemini restaurant picks against
[Qloo](https://qloo.com)’s taste graph, then repair weak lists from a closed
in-city dinner pool.

| | |
|---|---|
| **Live demo** | https://tasteguard-jew5ozur6q-uc.a.run.app |
| **Source** | https://github.com/prabhakaran-jm/tasteguard |
| **License** | MIT |

> Affinity cutoffs are **product policy** showing agreement with Qloo’s
> benchmark — not an official Qloo recommendation.

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

## Try the demo (judges)

1. Open the [live demo](https://tasteguard-jew5ozur6q-uc.a.run.app).
2. Leave the default **Stress test · Lisbon (recorded)** and press
   **Play recorded run** (~1s) — FAIL with Paris/Cascais/invented catches, then
   PASS after one closed-set repair.
3. Optionally **Run live** on **Stress test · Lisbon (live Qloo)** (~15–30s) for
   the same inject list against live Qloo.
4. NYC live is optional and slower (~30–45s); watch the step labels.

## Taste policy

An item is **ALLOW** when it beats **≥40%** of the in-city restaurant anchor set
(±5% borderline band). Categories must look like dinner restaurants (not
café-/bar-only). Wrong-city matches become **REWRITE**; unresolved names become
**UNVERIFIED** / unscored. Incomplete repaired lists never PASS.

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

## API (staged)

- `GET /api/health`
- `GET /api/presets`
- `POST /api/propose` → `POST /api/evaluate` → `POST /api/repair`

## MCP (agent tool surface)

Thin FastMCP (official `mcp.server.fastmcp`) mounted at **`/mcp`**.

| | |
|---|---|
| **SSE URL** | `https://tasteguard-jew5ozur6q-uc.a.run.app/mcp/sse` |
| **Tools** | `tasteguard_list_presets`, `tasteguard_evaluate`, `tasteguard_repair` |

Example Cursor / Claude Desktop remote server entry:

```json
{
  "mcpServers": {
    "tasteguard": {
      "url": "https://tasteguard-jew5ozur6q-uc.a.run.app/mcp/sse"
    }
  }
}
```

Tools wrap the same `TasteGuardService` as the HTTP API (Qloo evaluate + closed-set repair).

Recorded fixtures under `recorded/` are captured from live Qloo runs with
entity IDs scrubbed for the public repo.

## License

MIT — see [LICENSE](LICENSE).
