from __future__ import annotations

import re

from rapidfuzz import fuzz
from unidecode import unidecode

# Dining-type / article tokens stripped for identity. Keep "wine" — otherwise
# "Prado" collapses to the same bag as "Prado Wine Bar".
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


def _token_coverage(query_norm: str, candidate_norm: str) -> float:
    """Fraction of all query tokens found in the candidate (any length)."""
    q_tokens = _tokens(query_norm)
    if not q_tokens:
        return 0.0
    c_set = set(_tokens(candidate_norm))
    hits = sum(1 for t in q_tokens if t in c_set)
    return hits / len(q_tokens)


def _extra_token_penalty(query_norm: str, candidate_norm: str) -> float:
    """Penalize unmatched candidate tokens (Prado vs Prado Wine …)."""
    q_tokens = _tokens(query_norm)
    c_tokens = _tokens(candidate_norm)
    if not q_tokens or not c_tokens:
        return 0.0
    q_set = set(q_tokens)
    extras = [t for t in c_tokens if t not in q_set]
    if not extras:
        return 1.0
    return len(q_tokens) / len(c_tokens)


def name_similarity(a: str, b: str) -> float:
    """Conservative similarity for place identity.

    min(token_set, token_sort) × query coverage × extra-token penalty so a
    one-word query cannot perfectly match a longer distinct venue name.
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    set_score = fuzz.token_set_ratio(na, nb) / 100.0
    sort_score = fuzz.token_sort_ratio(na, nb) / 100.0
    base = min(set_score, sort_score)
    coverage = _token_coverage(na, nb)
    penalty = _extra_token_penalty(na, nb)
    return base * coverage * penalty


def names_match(a: str, b: str, threshold: float) -> bool:
    return name_similarity(a, b) >= threshold
