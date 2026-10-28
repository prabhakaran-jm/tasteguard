from __future__ import annotations

from typing import Any

from app.geo import LatLng

# Fixed Lisbon dinner demos — Day 3 may add recorded playback under the same ids.
PRESETS: dict[str, dict[str, Any]] = {
    "radiohead-lisbon": {
        "id": "radiohead-lisbon",
        "label": "Radiohead · Lisbon dinner",
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
    },
}


def list_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": p["id"],
            "label": p["label"],
            "city": p["city"],
            "persona": p["persona"],
        }
        for p in PRESETS.values()
    ]


def get_preset(preset_id: str) -> dict[str, Any] | None:
    return PRESETS.get(preset_id)


def preset_center(preset: dict[str, Any]) -> LatLng:
    c = preset["city_center"]
    return LatLng(lat=float(c["lat"]), lon=float(c["lon"]))
