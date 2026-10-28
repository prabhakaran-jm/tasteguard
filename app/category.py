from __future__ import annotations

from typing import Any

# Must appear in name or primary_genre (not arbitrary tags / long descriptions).
DINING_NAME_OR_GENRE = {
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
    "gastropub",
    "steakhouse",
    "pizzeria",
    "bakery",
    "wine bar",
    "tapas",
    "seafood",
    "sushi",
    "ramen",
    "grill",
    "kitchen",
    "trattoria",
    "osteria",
}

HARD_REJECT_NAME = {
    "museum",
    "museu",
    "miradouro",
    "viewpoint",
    "gallery",
    "galeria",
    "igreja",
    "church",
    "cathedral",
    "stadium",
    "airport",
    "hospital",
    "university",
    "universidade",
    "foundation",
    "fundação",
    "fundacao",
    "monument",
    "park",
    "jardim",
    " garden",
    "street",
    " avenue",
    "rua ",
    "travessa",
    "hotel",
    "hostel",
    "bookstore",
    "livraria",
    "theatre",
    "theater",
    "teatro",
}

# Cultural "casa …" without an explicit dining word in the name.
CULTURAL_CASA_BLOCKLIST = {
    "casa fernando pessoa",
    "casa dos bicos",
    "casa alorna",
}


def _name(entity: dict[str, Any]) -> str:
    return str(entity.get("name") or "").casefold()


def _primary_genre(entity: dict[str, Any]) -> str:
    props = entity.get("properties") or {}
    val = props.get("primary_genre") or entity.get("primary_genre")
    if isinstance(val, dict):
        return str(val.get("name") or "").casefold()
    if isinstance(val, str):
        return val.casefold()
    return ""


def _has_dining_signal(name: str, genre: str) -> bool:
    blob = f"{name} {genre}"
    return any(h in blob for h in DINING_NAME_OR_GENRE)


def is_restaurant_like(entity: dict[str, Any]) -> bool:
    """Strict dinner-venue check for anchors, alternatives, and verified meals.

    Requires an explicit dining cue in the **name** or **primary_genre**.
    Tags and long descriptions are ignored (too noisy on Qloo place records).
    """
    name = _name(entity)
    genre = _primary_genre(entity)

    if any(token in name for token in HARD_REJECT_NAME):
        if not _has_dining_signal(name, ""):
            return False

    if name.strip() in CULTURAL_CASA_BLOCKLIST:
        return False
    if name.startswith("casa ") and not _has_dining_signal(name, ""):
        # "Casa Fernando Pessoa" etc. — cultural houses without cafe/restaurant in name
        return False

    return _has_dining_signal(name, genre)


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
