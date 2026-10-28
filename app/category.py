from __future__ import annotations

from typing import Any

# Strong dinner cues — cafe/bakery alone is not enough for a dinner list.
DINNER_NAME_OR_GENRE = {
    "restaurant",
    "restaurante",
    "dining",
    "eatery",
    "bistro",
    "brasserie",
    "tasca",
    "taberna",
    "cervejaria",
    "gastropub",
    "steakhouse",
    "pizzeria",
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

# Weaker cues — only count when paired with a dinner cue above.
WEAK_DINING = {"cafe", "café", "bakery", "pastelaria", "padaria", "bar"}

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
    "palace",
    "palacio",
    "palácio",
    "bookstore",
    "livraria",
    "theatre",
    "theater",
    "teatro",
    "library",
    "coffee library",
    "associação",
    "associacao",
    "association",
    " naval",
    "yacht",
    "clube",
    "club ",
    " club",
}

# Cafe/bar alone is not enough for a dinner list when the venue reads as lodging.
LODGING_HINTS = ("hotel", "hostel", "palace", "palacio", "palácio", "belmonte")

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


def _has_dinner_signal(name: str, genre: str) -> bool:
    blob = f"{name} {genre}"
    return any(h in blob for h in DINNER_NAME_OR_GENRE)


def is_restaurant_like(entity: dict[str, Any]) -> bool:
    """Strict dinner-venue check for anchors, alternatives, and verified meals.

    Requires an explicit **dinner** cue in the name or primary_genre.
    Cafe/coffee/club/association venues are rejected for the dinner list.
    """
    name = _name(entity)
    genre = _primary_genre(entity)
    blob = f"{name} {genre}"

    if any(token in name for token in HARD_REJECT_NAME):
        return False
    if any(token in genre for token in ("association", "club", "naval", "museum")):
        return False

    if name.strip() in CULTURAL_CASA_BLOCKLIST:
        return False
    if name.startswith("casa ") and not _has_dinner_signal(name, ""):
        return False

    if not _has_dinner_signal(name, genre):
        return False

    lodging = any(h in name for h in LODGING_HINTS) or any(
        h in genre for h in LODGING_HINTS
    )
    if lodging and "restaurant" not in name and "restaurant" not in genre:
        return False

    if "library" in name:
        return False
    if "coffee" in name and "restaurant" not in blob:
        return False
    # Historic cafés (e.g. Nicola) often have genre "Cafe" only — not dinner.
    if any(w in blob for w in WEAK_DINING) and not _has_dinner_signal(name, genre):
        return False
    if genre.strip() in {"cafe", "café", "coffee shop", "coffeehouse", "bakery"}:
        return False
    return True


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
