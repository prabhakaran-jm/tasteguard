from __future__ import annotations

import re

from rapidfuzz import fuzz
from unidecode import unidecode

GENERIC_TOKENS = {
    "restaurant",
    "restaurante",
    "cafe",
    "café",
    "bar",
    "bistro",
    "taberna",
    "cervejaria",
    "tasca",
    "the",
    "a",
    "o",
    "da",
    "do",
    "de",
    "e",
    "and",
    "hotel",
    "hostel",
    "inn",
    "kitchen",
    "grill",
    "house",
}


def normalize_name(name: str) -> str:
    text = unidecode(name or "").casefold()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = [t for t in text.split() if t and t not in GENERIC_TOKENS]
    return " ".join(tokens)


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    # token_set_ratio handles "Cervejaria Ramiro" vs "Ramiro"
    return fuzz.token_set_ratio(na, nb) / 100.0


def names_match(a: str, b: str, threshold: float) -> bool:
    return name_similarity(a, b) >= threshold
