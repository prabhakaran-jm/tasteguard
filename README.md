# TasteGuard

Cultural quality gate for travel, dining, and hotel concierge agents.

AI agents can recommend a restaurant in the wrong city or one that completely
misses your tastes, without explaining why. **TasteGuard** verifies suggestions
against [Qloo](https://qloo.com)’s taste graph, explains affinity contributions,
and repairs weak recommendations using trusted in-city alternatives.

> Affinity cutoffs used by this project are **product policy**, not an official
> Qloo recommendation.

## Status

Steps 1–5 (CLI evaluate + Gemini closed-set repair) are in. Step 6 adds a
staged FastAPI JSON API and a Vite/React demo SPA (propose → evaluate → repair).

## Setup (local)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Edit .env and set QLOO_API_KEY (and later GEMINI_API_KEY)
```

## Run Day-1 Qloo probes

Requires a valid hackathon key in `.env` (`QLOO_API_KEY`).  
Uses `https://hackathon.api.qloo.com` with the `X-Api-Key` header.

```powershell
.\.venv\Scripts\activate
python probes\run_probes.py
```

Writes `probes/probe_report.json` (gitignored). Review the console summary and the JSON before locking any scoring policy.

**Search note:** `/search` uses `types=` (not `filter.type`). Location filters must be `lat,lon`, not a city name.

## CLI evaluate (Step 4)

```powershell
.\.venv\Scripts\activate
python -m app evaluate -c "Cervejaria Ramiro" -c "The French Laundry" -s artist:Radiohead
python -m app evaluate --json -c "Cervejaria Ramiro" -c "The French Laundry"
# Equivalent: python -m app.cli evaluate ...
```

Prints `evaluation_status` (`completed` / `unavailable` / `partial`) and `policy_verdict` (`PASS` / `FAIL` only when completed).  
Affinity cutoffs are **anchor-relative product policy** (default: beat 40% of in-city restaurant anchors).

## Gemini demo + closed-set repair (Step 5)

Requires `GEMINI_API_KEY` and `QLOO_API_KEY` in `.env`.

```powershell
python -m app demo -s artist:Radiohead
python -m app demo --json -s artist:Radiohead --max-rounds 3
```

Flow:

1. **Unguarded:** Gemini Flash, no tools → structured place list (name + neighbourhood)
2. **TasteGuard evaluate** → evidence + allow/rewrite/unknown + PASS/FAIL
3. **Closed-set repair** (max 3): agent may only pick Qloo alternative `entity_id`s from the FAIL pool, then re-evaluate

## Demo UI (Step 6)

Staged API (not one long spinner):

1. `POST /api/propose` — Gemini unguarded list  
2. `POST /api/evaluate` — TasteGuard verdict + `evaluation_id` (cached ~5 min)  
3. `POST /api/repair` — closed-set repair from that cached FAIL (history on this response only)

Every demo JSON response includes `mode` (`live` today; `recorded` on Day 3).  
`unavailable` / `partial` / HTTP errors must never be styled like PASS in the UI.

### Local (iterate)

```powershell
# terminal A — API
.\.venv\Scripts\activate
$env:PYTHONPATH='.'
uvicorn app.main:app --reload --port 8000

# terminal B — Vite (proxies /api → :8000; no CORS middleware)
cd web
npm install
npm run dev
```

Open the Vite URL (usually `http://127.0.0.1:5173`).

### Local (prod-shaped: one process)

```powershell
cd web
npm run build
cd ..
.\.venv\Scripts\activate
$env:PYTHONPATH='.'
uvicorn app.main:app --port 8000
```

Open `http://127.0.0.1:8000` — FastAPI serves `web/dist` after `/api/*`.

### Cloud Run source upload

`web/dist` is **gitignored**. Build it locally before deploy. [`.gcloudignore`](.gcloudignore)
is a denylist: it honors `.gitignore`, then re-admits `web/dist/**`, and excludes
`web/node_modules/`. **Dry-run once before Day 3** and confirm `web/dist/index.html`
is in the upload set (a missing dist only shows up as a blank live page).

### React timebox (Day 2)

If the SPA is not rendering live API data by **15:00 local, Wed Oct 29**, drop to
Jinja templates and keep the same `web/src/styles.css` (shared stylesheet).

## License

MIT — see [LICENSE](LICENSE).
