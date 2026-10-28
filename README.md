# TasteGuard

Cultural quality gate for travel, dining, and hotel concierge agents.

AI agents can recommend a restaurant in the wrong city or one that completely
misses your tastes, without explaining why. **TasteGuard** verifies suggestions
against [Qloo](https://qloo.com)’s taste graph, explains affinity contributions,
and repairs weak recommendations using trusted in-city alternatives.

> Affinity cutoffs used by this project are **product policy**, not an official
> Qloo recommendation.

## Status

Foundation scaffold only. Application modules land in later steps.

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

## License

MIT — see [LICENSE](LICENSE).
