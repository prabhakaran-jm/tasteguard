from __future__ import annotations

from typing import Any, Literal

from app.geo import LatLng
from app.models import CandidateInput

PresetKind = Literal["recorded", "stress", "live"]

# Multi-seed personas so explainability contributions vary card-to-card.
_RADIOHEAD_ARTSY_SEEDS = [
    {"query": "Radiohead", "types": "urn:entity:artist"},
    {"query": "There Will Be Blood", "types": "urn:entity:movie"},
    {"query": "Norwegian Wood", "types": "urn:entity:book"},
    {"query": "Aesop", "types": "urn:entity:brand"},
]

# Stress inject: two keepers that clear the 40th-percentile taste policy in live
# Qloo runs, plus wrong-city + invented catches. Neighbourhoods claim Lisbon so
# the Paris/Cascais distance reveal is a real catch.
_STRESS_INJECT = [
    {"name": "A Cevicheria", "neighbourhood": "Príncipe Real"},
    {"name": "Cervejaria Ramiro", "neighbourhood": "Intendente"},
    {"name": "Le Comptoir du Relais", "neighbourhood": "Chiado"},
    {"name": "Fortaleza do Guincho", "neighbourhood": "Bairro Alto"},
    {"name": "Casa Azul da Lua Fictícia", "neighbourhood": "Alfama"},
]


PRESETS: dict[str, dict[str, Any]] = {
    "stress-lisbon-recorded": {
        "id": "stress-lisbon-recorded",
        "label": "Stress test · Lisbon (recorded) — shows the catch",
        "kind": "recorded",
        "city": "Lisbon",
        "city_center": {"lat": 38.7223, "lon": -9.1393},
        "persona": (
            "Indie / artsy palate; thoughtful local dining. Seeds: Radiohead, "
            "There Will Be Blood, Norwegian Wood, Aesop."
        ),
        "seed_queries": list(_RADIOHEAD_ARTSY_SEEDS),
        "n": 5,
        "recorded_path": "recorded/stress-lisbon.json",
        "blurb": (
            "Recorded replay of a live Qloo stress run: two in-city keepers, a "
            "Paris venue claiming Chiado, a Cascais venue claiming Bairro Alto, "
            "and an invented name — then closed-set repair to five ALLOW places."
        ),
    },
    "stress-lisbon-live": {
        "id": "stress-lisbon-live",
        "label": "Stress test · Lisbon (live Qloo) — injects Paris + Cascais",
        "kind": "stress",
        "city": "Lisbon",
        "city_center": {"lat": 38.7223, "lon": -9.1393},
        "persona": (
            "Indie / artsy palate; thoughtful local dining. Seeds: Radiohead, "
            "There Will Be Blood, Norwegian Wood, Aesop."
        ),
        "seed_queries": list(_RADIOHEAD_ARTSY_SEEDS),
        "n": 5,
        "inject_candidates": list(_STRESS_INJECT),
        "blurb": (
            "Injected test list (not Gemini). Deliberately includes wrong-city "
            "and invented names, then runs live Qloo evaluate + repair."
        ),
    },
    "radiohead-nyc": {
        "id": "radiohead-nyc",
        "label": "Radiohead · New York dinner (live) — optional, slower",
        "kind": "live",
        "city": "New York",
        "city_center": {"lat": 40.7128, "lon": -74.0060},
        "persona": (
            "Indie / artsy palate in New York; thoughtful local dining, "
            "not tourist traps. Seeds: Radiohead, There Will Be Blood, "
            "Norwegian Wood, Aesop."
        ),
        "seed_queries": list(_RADIOHEAD_ARTSY_SEEDS),
        "n": 5,
        "blurb": (
            "Optional live Gemini → TasteGuard path for New York. Often ~30–45s — "
            "watch the step labels; prefer the recorded stress demo for a fast catch."
        ),
    },
    "radiohead-lisbon": {
        "id": "radiohead-lisbon",
        "label": "Radiohead · Lisbon dinner (live)",
        "kind": "live",
        "city": "Lisbon",
        "city_center": {"lat": 38.7223, "lon": -9.1393},
        "persona": (
            "Indie / artsy palate; prefers thoughtful local dining, "
            "not tourist traps. Seeds: Radiohead, There Will Be Blood, "
            "Norwegian Wood, Aesop."
        ),
        "seed_queries": list(_RADIOHEAD_ARTSY_SEEDS),
        "n": 5,
        "blurb": (
            "Honest live Gemini propose → TasteGuard. Use a stress preset to "
            "guarantee the wrong-city catch."
        ),
    },
}


def list_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": p["id"],
            "label": p["label"],
            "kind": p["kind"],
            "city": p["city"],
            "persona": p["persona"],
            "blurb": p.get("blurb") or "",
            "default": p["id"] == "stress-lisbon-recorded",
        }
        for p in PRESETS.values()
    ]


def get_preset(preset_id: str) -> dict[str, Any] | None:
    return PRESETS.get(preset_id)


def preset_center(preset: dict[str, Any]) -> LatLng:
    c = preset["city_center"]
    return LatLng(lat=float(c["lat"]), lon=float(c["lon"]))


def inject_candidates(preset: dict[str, Any]) -> list[CandidateInput]:
    raw = preset.get("inject_candidates") or []
    out: list[CandidateInput] = []
    for item in raw:
        out.append(
            CandidateInput(
                name=str(item["name"]),
                neighbourhood=item.get("neighbourhood"),
                address=item.get("address"),
                notes=item.get("notes"),
            )
        )
    return out
