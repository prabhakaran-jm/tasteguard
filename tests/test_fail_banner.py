"""FAIL banner prefers failure-type evidence over generic match lines."""

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


def test_banner_prefers_taste_cutoff_over_matched_line():
    scored = ScoredCandidate(
        input=CandidateInput(name="Prado"),
        evidence=EvidenceState.VERIFIED,
        item_verdict=ItemVerdict.REWRITE,
        matched_name="Prado",
        distance_km=1.4,
        affinity=0.5,
        anchor_percentile=0.26,
        reasons=[
            "Matched Qloo place 'Prado' (1.4 km from Lisbon)",
            "Beats 26% of in-city restaurant anchors (needs 40%)",
        ],
    )
    text = _banner_reason(scored)
    assert "26%" in text or "needs 40%" in text
    assert "Matched Qloo place" not in text


def test_banner_prefers_unscored_over_matched_line():
    scored = ScoredCandidate(
        input=CandidateInput(name="Senhor Uva"),
        evidence=EvidenceState.VERIFIED,
        item_verdict=ItemVerdict.UNKNOWN,
        matched_name="Senhor Uva",
        distance_km=1.0,
        reasons=[
            "Matched Qloo place 'Senhor Uva' (1.0 km from Lisbon)",
            "Qloo returned no taste score — unscored",
        ],
    )
    text = _banner_reason(scored)
    assert "no taste score" in text.lower() or "unscored" in text.lower()
    assert "Matched Qloo place" not in text


def test_banner_prefers_category_over_wrong_city_synthetic():
    scored = ScoredCandidate(
        input=CandidateInput(name="Katz's Delicatessen"),
        evidence=EvidenceState.MISMATCH,
        item_verdict=ItemVerdict.REWRITE,
        matched_name="Katz's Delicatessen",
        distance_km=1.9,
        reasons=[
            "Matched 'Katz's Delicatessen' within 1.9 km of New York "
            "but category is not restaurant-like",
        ],
    )
    text = _banner_reason(scored)
    assert "restaurant-like" in text.lower() or "category" in text.lower()
    assert "wrong city" not in text.lower()


def test_banner_falls_back_to_no_confident_match():
    scored = ScoredCandidate(
        input=CandidateInput(name="Casa Azul da Lua Fictícia"),
        evidence=EvidenceState.NO_CONFIDENT_MATCH,
        item_verdict=ItemVerdict.UNKNOWN,
        reasons=["No confident Qloo match"],
    )
    assert _banner_reason(scored) == "No confident Qloo match"
