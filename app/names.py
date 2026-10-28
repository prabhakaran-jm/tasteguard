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


def _tokens(normalized: str) -> list[str]:
    return [t for t in normalized.split() if t]


def _distinctive_coverage(query_norm: str, candidate_norm: str) -> float:
    """Fraction of distinctive query tokens (len>=4) found in the candidate.

    Prevents "The French Laundry" matching "French Arth" on the shared "french"
    token alone.
    """
    q_tokens = [t for t in _tokens(query_norm) if len(t) >= 4]
    if not q_tokens:
        # Fall back to all tokens if none are long enough
        q_tokens = _tokens(query_norm)
    if not q_tokens:
        return 0.0
    c_set = set(_tokens(candidate_norm))
    hits = sum(1 for t in q_tokens if t in c_set)
    return hits / len(q_tokens)


def name_similarity(a: str, b: str) -> float:
    """Conservative similarity for place identity.

    Uses the minimum of token-set and token-sort ratios, then multiplies by
    distinctive-token coverage so a single shared word cannot pass the gate.
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    set_score = fuzz.token_set_ratio(na, nb) / 100.0
    sort_score = fuzz.token_sort_ratio(na, nb) / 100.0
    base = min(set_score, sort_score)
    coverage = _distinctive_coverage(na, nb)
    return base * coverage


def names_match(a: str, b: str, threshold: float) -> bool:
    return name_similarity(a, b) >= threshold
