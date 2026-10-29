from __future__ import annotations

from typing import Any

# Positive dinner cues — required for the dinner list (name or primary_genre).
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
    "steak house",
    "deli",
    "delicatessen",
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

# Always reject — even when the name also has a dinner cue.
HARD_REJECT_ALWAYS = {
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
    "hotel",
    "hostel",
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
}

# Street/park/palace words — skip when the name already looks like dinner
# (e.g. Taberna da Rua das Flores).
HARD_REJECT_LOCATION = {
    "park",
    "jardim",
    " garden",
    "street",
    " avenue",
    "rua ",
    "travessa",
    "palace",
    "palacio",
    "palácio",
}

HARD_REJECT_NAME = HARD_REJECT_ALWAYS | HARD_REJECT_LOCATION

# Bar/cafe-only genres without a dinner cue are not dinner restaurants.
BAR_OR_CAFE_ONLY = {
    "bar",
    "pub",
    "nightlife",
    "nightclub",
    "cocktail bar",
    "lounge",
    "cafe",
    "café",
    "coffee shop",
    "coffeehouse",
    "bakery",
    "pastelaria",
    "padaria",
}

LODGING_HINTS = ("hotel", "hostel", "palace", "palacio", "palácio", "belmonte")

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


# Historic cafés / specialty coffee that Qloo sometimes tags with a noisy dining genre.
KNOWN_NON_DINNER_NAMES = {
    "nicola",
    "café nicola",
    "cafe nicola",
    "the mill",
}

# Stronger cues required for the closed-set *repair pool* (not mere "kitchen"/"grill").
POOL_DINNER_CUES = {
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
    "steak house",
    "deli",
    "delicatessen",
    "pizzeria",
    "wine bar",
    "tapas",
    "seafood",
    "sushi",
    "ramen",
    "trattoria",
    "osteria",
}


def is_dinner_pool_eligible(entity: dict[str, Any]) -> bool:
    """Stricter gate for repair alternatives: positive dinner metadata required."""
    if not is_restaurant_like(entity):
        return False
    name = _name(entity)
    if name in KNOWN_NON_DINNER_NAMES or name.startswith("nicola "):
        return False
    # Bare "* Bar" names (Snob Bar) — not dinner even if Qloo genre is noisy.
    if name.rstrip().endswith(" bar") and "wine bar" not in name:
        return False
    # Cafés stay out unless the name itself also carries a dinner word.
    if ("cafe" in name or "café" in name) and not any(
        x in name
        for x in ("restaurant", "restaurante", "taberna", "bistro", "bistrô")
    ):
        return False
    if " show" in name or name.endswith("show") or "concert" in name:
        return False
    genre = _primary_genre(entity)
    blob = f"{name} {genre}"
    return any(cue in blob for cue in POOL_DINNER_CUES)


def is_restaurant_like(entity: dict[str, Any]) -> bool:
    """Strict dinner-venue check for anchors, alternatives, and verified meals.

    Requires positive restaurant/dining evidence in the name or primary_genre.
    Bar-only or cafe-only venues are rejected even if they serve drinks/snacks.
    Names containing \"bar\" are fine when paired with dinner evidence
    (e.g. wine bar, gastropub, taberna).
    """
    name = _name(entity)
    genre = _primary_genre(entity)
    blob = f"{name} {genre}"

    if name in KNOWN_NON_DINNER_NAMES or name.startswith("nicola "):
        return False
    if any(token in name for token in HARD_REJECT_ALWAYS):
        return False
    dinnerish = _has_dinner_signal(name, genre)
    # Location words (rua/park/palace) only block when there is no dinner cue.
    if not dinnerish and any(token in name for token in HARD_REJECT_LOCATION):
        return False
    if any(token in genre for token in ("association", "club", "naval", "museum")):
        return False

    if name.strip() in CULTURAL_CASA_BLOCKLIST:
        return False
    if name.startswith("casa ") and not _has_dinner_signal(name, ""):
        return False

    # Positive dinner evidence required — not merely "not a museum".
    if not dinnerish:
        return False

    lodging = any(h in name for h in LODGING_HINTS) or any(
        h in genre for h in LODGING_HINTS
    )
    if lodging and "restaurant" not in name and "restaurant" not in genre:
        return False

    if "library" in name or "coffee" in name:
        if "restaurant" not in blob:
            return False

    genre_stripped = genre.strip()
    if genre_stripped in BAR_OR_CAFE_ONLY:
        return False
    # \"Snob Bar\" / bare cocktail bars: dinner cue must not be only a weak substring.
    if name.rstrip().endswith(" bar") and "wine bar" not in name:
        if "restaurant" not in genre and "gastropub" not in blob:
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
