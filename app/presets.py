from __future__ import annotations

from typing import Any, Literal

from app.geo import LatLng
from app.models import CandidateInput

PresetKind = Literal["recorded", "stress", "live"]


PRESETS: dict[str, dict[str, Any]] = {
    # Default judge path — always shows wrong-city + invent catches (no live Gemini).
    "stress-lisbon-recorded": {
        "id": "stress-lisbon-recorded",
        "label": "Stress test · Lisbon (recorded) — shows the catch",
        "kind": "recorded",
        "city": "Lisbon",
        "city_center": {"lat": 38.7223, "lon": -9.1393},
        "persona": (
            "Indie / artsy palate; prefers thoughtful local dining. "
            "Affinity leans toward Radiohead."
        ),
        "seed_queries": [
            {"query": "Radiohead", "types": "urn:entity:artist"},
        ],
        "n": 5,
        "recorded_path": "recorded/stress-lisbon.json",
        "blurb": (
            "Fixed card: two good Lisbon picks, a Paris restaurant, a Cascais "
            "restaurant, and an invented name — so TasteGuard’s catch always runs."
        ),
    },
    # Same inject list, live Qloo evaluate (burns quota; labelled honestly).
    "stress-lisbon-live": {
        "id": "stress-lisbon-live",
        "label": "Stress test · Lisbon (live Qloo) — injects Paris + Cascais",
        "kind": "stress",
        "city": "Lisbon",
        "city_center": {"lat": 38.7223, "lon": -9.1393},
        "persona": (
            "Indie / artsy palate; prefers thoughtful local dining. "
            "Affinity leans toward Radiohead."
        ),
        "seed_queries": [
            {"query": "Radiohead", "types": "urn:entity:artist"},
        ],
        "n": 5,
        "inject_candidates": [
            {"name": "Prado", "neighbourhood": "Sé"},
            {"name": "O Velho Eurico", "neighbourhood": "Mouraria"},
            {
                "name": "Le Comptoir du Relais",
                "neighbourhood": "6th arrondissement, Paris",
            },
            {"name": "Fortaleza do Guincho", "neighbourhood": "Cresmina, Cascais"},
            {
                "name": "Casa Azul da Lua Fictícia",
                "neighbourhood": "Alfama",
            },
        ],
        "blurb": (
            "Does not call Gemini. Injects known wrong-city and invented names, "
            "then runs live Qloo evaluate + repair."
        ),
    },
    "radiohead-nyc": {
        "id": "radiohead-nyc",
        "label": "Radiohead · New York dinner (live)",
        "kind": "live",
        "city": "New York",
        "city_center": {"lat": 40.7128, "lon": -74.0060},
        "persona": (
            "Indie / artsy palate in New York; thoughtful local dining, "
            "not tourist traps. Affinity leans toward Radiohead."
        ),
        "seed_queries": [
            {"query": "Radiohead", "types": "urn:entity:artist"},
        ],
        "n": 5,
        "blurb": "Honest live Gemini → TasteGuard path for New York.",
    },
    "radiohead-lisbon": {
        "id": "radiohead-lisbon",
        "label": "Radiohead · Lisbon dinner (live)",
        "kind": "live",
        "city": "Lisbon",
        "city_center": {"lat": 38.7223, "lon": -9.1393},
        "persona": (
            "Indie / artsy palate; prefers thoughtful local dining, "
            "not tourist traps. Affinity leans toward Radiohead."
        ),
        "seed_queries": [
            {"query": "Radiohead", "types": "urn:entity:artist"},
        ],
        "n": 5,
        "blurb": (
            "Honest live run. At temperature 0 Gemini often picks good Lisbon "
            "spots — use a stress/recorded preset to guarantee the catch."
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
