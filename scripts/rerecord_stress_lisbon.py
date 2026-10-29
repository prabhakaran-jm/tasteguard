"""Capture recorded/stress-lisbon.json from a local live stress evaluate+repair.

Uses TasteGuardService (needs QLOO_API_KEY / GEMINI in .env). Fixture stays
gitignored — rewrite history is not required.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import CandidateInput, EvaluateRequest  # noqa: E402
from app.presets import get_preset, inject_candidates, preset_center  # noqa: E402
from app.service import TasteGuardService  # noqa: E402

OUT = ROOT / "recorded" / "stress-lisbon.json"


def _scrub_id(eid: str | None) -> str | None:
    if not eid:
        return None
    digest = hashlib.sha1(eid.encode("utf-8")).hexdigest()[:12]
    return f"rec-{digest}"


def _scrub_obj(obj: object) -> object:
    if isinstance(obj, dict):
        out: dict = {}
        for k, v in obj.items():
            if k == "entity_id" and isinstance(v, str):
                out[k] = _scrub_id(v)
            elif k in (
                "signal_ids",
                "anchor_sample",
                "anchor_ids",
                "scored_ids",
                "chosen_entity_ids",
            ):
                if isinstance(v, list):
                    out[k] = [_scrub_id(str(x)) if x else x for x in v]
                else:
                    out[k] = v
            elif k in ("signal_labels", "explainability") and isinstance(v, dict):
                out[k] = {_scrub_id(str(a)) or a: b for a, b in v.items()}
            else:
                out[k] = _scrub_obj(v)
        return out
    if isinstance(obj, list):
        return [_scrub_obj(x) for x in obj]
    if isinstance(obj, str) and re.fullmatch(
        r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}",
        obj,
    ):
        return _scrub_id(obj)
    return obj


def _dump_result(result) -> dict:
    return json.loads(result.model_dump_json())


async def main() -> None:
    preset = get_preset("stress-lisbon-live")
    assert preset is not None
    candidates = inject_candidates(preset)
    request = EvaluateRequest(
        city=str(preset["city"]),
        city_center=preset_center(preset),
        seed_queries=list(preset.get("seed_queries") or []),
        candidates=candidates,
        fetch_alternatives=True,
        expected_count=len(candidates),
    )
    service = TasteGuardService()
    initial = await service.evaluate(request)
    final, history = await service.repair_until_pass(
        request,
        persona_description=str(preset["persona"]),
        max_rounds=3,
        initial=initial,
    )
    assert initial.policy_verdict and initial.policy_verdict.value == "FAIL", initial.message
    assert final.policy_verdict and final.policy_verdict.value == "PASS", final.message

    eval_result = _dump_result(initial)
    repair_final = _dump_result(final)
    for block in (eval_result, repair_final):
        notes = dict(block.get("notes") or {})
        for key in (
            "signal_ids",
            "signal_labels",
            "anchor_sample",
            "anchor_ids",
            "scored_ids",
            "chosen_entity_ids",
        ):
            notes.pop(key, None)
        notes["captured_from"] = "live stress-lisbon-live"
        notes["entity_ids"] = "scrubbed for public fixture"
        block["notes"] = notes

    propose_cands = [
        CandidateInput(
            name=c.name,
            neighbourhood=c.neighbourhood,
            address=c.address,
            notes=c.notes,
            entity_id=None,
            pinned_distance_km=None,
            pinned_locality=None,
        ).model_dump()
        for c in candidates
    ]

    fixture = {
        "preset_id": "stress-lisbon-recorded",
        "mode": "recorded",
        "captured_at": date.today().isoformat(),
        "note": (
            "Captured from a live stress-lisbon-live PASS. Entity IDs scrubbed; "
            "affinities/percentiles from that live Qloo run. Injected list is not "
            "Gemini. Place names in this fixture are for replay only — do not "
            "republish scored Qloo rows in the README."
        ),
        "propose": {"candidates": propose_cands},
        "evaluate": _scrub_obj(eval_result),
        "repair": {
            "final": _scrub_obj(repair_final),
            "history_len": len(history),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    names = [c["input"]["name"] for c in repair_final["candidates"]]
    print(f"wrote {OUT}")
    print(f"FAIL: {initial.message}")
    print(f"PASS names: {names}")


if __name__ == "__main__":
    asyncio.run(main())
