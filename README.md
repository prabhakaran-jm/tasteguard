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

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set QLOO_API_KEY and GEMINI_API_KEY
```

## License

MIT — see [LICENSE](LICENSE).
