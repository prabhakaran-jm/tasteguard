from __future__ import annotations

from typing import Any

RESTAURANT_HINTS = {
    "restaurant",
    "restaurante",
    "dining",
    "eatery",
    "bistro",
    "cafe",
    "café",
    "brasserie",
    "tasca",
    "taberna",
    "cervejaria",
    "food",
    "cuisine",
    "fine dining",
    "gastropub",
    "steakhouse",
    "pizzeria",
    "bakery",
}

NON_RESTAURANT_HINTS = {
    "hotel",
    "hostel",
    "museum",
    "museu",
    "gallery",
    "park",
    "miradouro",
    "viewpoint",
    "stadium",
    "airport",
    "nightclub",
    "club",
    "spa",
    "gym",
    "church",
    "igreja",
    "monument",
}


def _collect_text(entity: dict[str, Any]) -> str:
    parts: list[str] = [str(entity.get("name") or "")]
    props = entity.get("properties") or {}
    for key in (
        "description",
        "short_description",
        "type",
        "subtype",
        "category",
        "primary_genre",
    ):
        val = props.get(key) or entity.get(key)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, dict) and val.get("name"):
            parts.append(str(val["name"]))
    tags = entity.get("tags") or props.get("tags") or []
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str):
                parts.append(tag)
            elif isinstance(tag, dict):
                parts.append(str(tag.get("name") or tag.get("id") or ""))
    subtype = entity.get("subtype")
    if isinstance(subtype, str):
        parts.append(subtype)
    return " ".join(parts).casefold()


def is_restaurant_like(entity: dict[str, Any]) -> bool:
    text = _collect_text(entity)
    has_food = any(h in text for h in RESTAURANT_HINTS)
    has_non = any(h in text for h in NON_RESTAURANT_HINTS)
    if has_non and not has_food:
        return False
    if has_food:
        return True
    # Ambiguous place with no clear tags: not treated as verified restaurant
    return False


def tag_names(entity: dict[str, Any]) -> list[str]:
    out: list[str] = []
    tags = entity.get("tags") or (entity.get("properties") or {}).get("tags") or []
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str):
                out.append(tag)
            elif isinstance(tag, dict) and tag.get("name"):
                out.append(str(tag["name"]))
    return out
