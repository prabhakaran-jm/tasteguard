"""FAIL banner prefers wrong-city / distance evidence over generic fallbacks."""

from __future__ import annotations

from app.models import (
    CandidateInput,
    EvidenceState,
    ItemVerdict,
    ScoredCandidate,
)
from app.service import _banner_reason


def test_banner_prefers_km_away_over_no_in_city_fallback():
    scored = ScoredCandidate(
        input=CandidateInput(name="Le Comptoir du Relais", neighbourhood="Chiado"),
        evidence=EvidenceState.MISMATCH,
        item_verdict=ItemVerdict.REWRITE,
        matched_name="Le Comptoir du Relais",
        distance_km=1452.0,
        reasons=[
            "Claimed Chiado; Qloo places 'Le Comptoir du Relais' 1452 km away in Paris",
            "No in-city name match found",
        ],
    )
    text = _banner_reason(scored)
    assert "1452 km away" in text
    assert "No in-city name match found" not in text


def test_banner_falls_back_to_first_reason():
    scored = ScoredCandidate(
        input=CandidateInput(name="Casa Azul da Lua Fictícia"),
        evidence=EvidenceState.NO_CONFIDENT_MATCH,
        item_verdict=ItemVerdict.UNKNOWN,
        reasons=["No confident Qloo match"],
    )
    assert _banner_reason(scored) == "No confident Qloo match"
