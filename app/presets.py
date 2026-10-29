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

# Contrasting persona — same city, different taste graph neighbourhood.
_STREET_CULTURE_SEEDS = [
    {"query": "Kendrick Lamar", "types": "urn:entity:artist"},
    {"query": "Uncut Gems", "types": "urn:entity:movie"},
    {"query": "Kitchen Confidential", "types": "urn:entity:book"},
    {"query": "Nike", "types": "urn:entity:brand"},
]

# Stress inject: keepers that clear the 40th-percentile taste policy in live
# Qloo runs, plus wrong-city + invented + a place that often fails *taste*
# (tourist chain) while still resolving in Lisbon.
_STRESS_INJECT = [
    {"name": "A Cevicheria", "neighbourhood": "Príncipe Real"},
    {"name": "Cervejaria Ramiro", "neighbourhood": "Intendente"},
    {"name": "Le Comptoir du Relais", "neighbourhood": "Chiado"},
    {"name": "Fortaleza do Guincho", "neighbourhood": "Bairro Alto"},
    {"name": "Casa Azul da Lua Fictícia", "neighbourhood": "Alfama"},
    # Live probe 2026-10-29: resolves in Lisbon (~1.4 km) but ~24th-percentile
    # vs Radiohead/artsy anchors — a Qloo taste miss, not a geo miss.
    {"name": "Prado", "neighbourhood": "Avenida da Liberdade"},
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
        "n": 6,
        "recorded_path": "recorded/stress-lisbon.json",
        "blurb": (
            "Recorded replay: two keepers, Paris (~1,452 km), Cascais (~29 km), "
            "an invented name, and Prado (in-city but weak taste fit) — then "
            "closed-set repair to validated dinner places."
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
        "n": 6,
        "inject_candidates": list(_STRESS_INJECT),
        "blurb": (
            "Injected test list (not Gemini). Wrong-city, invented, and Prado "
            "(resolves in Lisbon but fails the 40th-percentile taste bar)."
        ),
    },
    "radiohead-lisbon": {
        "id": "radiohead-lisbon",
        "label": "Radiohead · Lisbon dinner (live) — taste demo",
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
            "Recommended live demo: Gemini proposes for a Radiohead-leaning "
            "palate; TasteGuard scores taste vs Lisbon anchors (Qloo cross-domain "
            "graph) and repairs weak fits from a closed pool."
        ),
    },
    "kendrick-lisbon": {
        "id": "kendrick-lisbon",
        "label": "Kendrick · Lisbon dinner (live) — contrasting taste",
        "kind": "live",
        "city": "Lisbon",
        "city_center": {"lat": 38.7223, "lon": -9.1393},
        "persona": (
            "Street-smart, high-energy palate; bold flavours and nightlife-adjacent "
            "dining. Seeds: Kendrick Lamar, Uncut Gems, Kitchen Confidential, Nike."
        ),
        "seed_queries": list(_STREET_CULTURE_SEEDS),
        "n": 5,
        "blurb": (
            "Same city, different taste graph. Compare with Radiohead Lisbon to "
            "see Qloo change which dinners clear the bar."
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
            "prefer Radiohead Lisbon or the recorded stress demo for a fast pitch."
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
            # Keep recorded as one-click FAIL→PASS; Hero guide starts there.
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
