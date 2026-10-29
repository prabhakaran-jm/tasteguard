"""Offline repair invariants with a fake evaluate / Gemini (no Qloo)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.geo import LatLng
from app.models import (
    Alternative,
    CandidateInput,
    EvaluateRequest,
    EvaluationResult,
    EvaluationStatus,
    EvidenceState,
    ItemVerdict,
    PolicyVerdict,
    ScoredCandidate,
)
from app.service import TasteGuardService


def _scored(
    name: str,
    verdict: ItemVerdict,
    *,
    entity_id: str | None = None,
    evidence: EvidenceState = EvidenceState.VERIFIED,
) -> ScoredCandidate:
    return ScoredCandidate(
        input=CandidateInput(name=name),
        evidence=evidence,
        item_verdict=verdict,
        matched_name=name if evidence == EvidenceState.VERIFIED else None,
        entity_id=entity_id,
        distance_km=1.0 if entity_id else None,
        reasons=["test"],
    )


def _fail_initial() -> EvaluationResult:
    alts = [
        Alternative(
            entity_id=f"alt-{i}",
            name=f"Alt {i}",
            affinity=0.9 - i * 0.01,
            distance_km=1.0,
            locality="Lisbon",
        )
        for i in range(5)
    ]
    return EvaluationResult(
        evaluation_status=EvaluationStatus.COMPLETED,
        policy_verdict=PolicyVerdict.FAIL,
        city="Lisbon",
        candidates=[
            _scored("Keeper A", ItemVerdict.ALLOW, entity_id="keep-a"),
            _scored("Keeper B", ItemVerdict.ALLOW, entity_id="keep-b"),
            _scored(
                "Bad Far",
                ItemVerdict.REWRITE,
                evidence=EvidenceState.MISMATCH,
            ),
            _scored(
                "Bad Far 2",
                ItemVerdict.REWRITE,
                evidence=EvidenceState.MISMATCH,
            ),
            _scored(
                "Invented",
                ItemVerdict.UNKNOWN,
                evidence=EvidenceState.NO_CONFIDENT_MATCH,
            ),
        ],
        alternatives=alts,
        anchor_count=10,
        message="FAIL",
        notes={"anchor_ids": ["a1", "a2"], "anchor_city": "Lisbon"},
    )


@pytest.mark.asyncio
async def test_repair_keeps_allows_preserves_length_and_pass_all_allow():
    initial = _fail_initial()
    request = EvaluateRequest(
        city="Lisbon",
        city_center=LatLng(lat=38.72, lon=-9.14),
        seed_queries=[],
        candidates=[c.input for c in initial.candidates],
        expected_count=5,
    )

    pass_result = EvaluationResult(
        evaluation_status=EvaluationStatus.COMPLETED,
        policy_verdict=PolicyVerdict.PASS,
        city="Lisbon",
        candidates=[
            _scored("Keeper A", ItemVerdict.ALLOW, entity_id="keep-a"),
            _scored("Keeper B", ItemVerdict.ALLOW, entity_id="keep-b"),
            _scored("Alt 0", ItemVerdict.ALLOW, entity_id="alt-0"),
            _scored("Alt 1", ItemVerdict.ALLOW, entity_id="alt-1"),
            _scored("Alt 2", ItemVerdict.ALLOW, entity_id="alt-2"),
        ],
        alternatives=[],
        anchor_count=10,
        message="PASS",
        notes={"anchor_ids": ["a1", "a2"]},
    )

    service = TasteGuardService(Settings())
    gemini = MagicMock()
    gemini.repair_from_pool = AsyncMock(return_value=["alt-0", "alt-1", "alt-2"])
    evaluate_mock = AsyncMock(return_value=pass_result)

    with patch("app.gemini_agent.GeminiConcierge", return_value=gemini):
        with patch.object(service, "evaluate", new=evaluate_mock):
            final, history = await service.repair_until_pass(
                request,
                persona_description="test",
                max_rounds=1,
                initial=initial,
            )

    assert len(final.candidates) == 5
    assert final.policy_verdict == PolicyVerdict.PASS
    assert all(c.item_verdict == ItemVerdict.ALLOW for c in final.candidates)
    evaluate_mock.assert_awaited()
    eval_req = evaluate_mock.await_args.args[0]
    keep_names = {c.name for c in eval_req.candidates[:2]}
    assert keep_names == {"Keeper A", "Keeper B"}
    assert len(eval_req.candidates) == 5
    assert len(history) >= 2


@pytest.mark.asyncio
async def test_repair_short_pool_does_not_fabricate_pass():
    initial = _fail_initial()
    initial.alternatives = []  # empty pool
    request = EvaluateRequest(
        city="Lisbon",
        city_center=LatLng(lat=38.72, lon=-9.14),
        seed_queries=[],
        candidates=[c.input for c in initial.candidates],
        expected_count=5,
    )

    service = TasteGuardService(Settings())
    gemini = MagicMock()
    gemini.repair_from_pool = AsyncMock(return_value=[])

    empty_alts = AsyncMock(return_value=[])
    with patch("app.gemini_agent.GeminiConcierge", return_value=gemini):
        with patch("app.service.QlooClient") as qloo_cls:
            qloo_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            qloo_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch.object(service, "resolve_seeds", new=AsyncMock(return_value=([], {}))):
                with patch("app.service.AnchorScorer") as scorer_cls:
                    scorer_cls.return_value.fetch_alternatives = empty_alts
                    final, history = await service.repair_until_pass(
                        request,
                        persona_description="test",
                        max_rounds=1,
                        initial=initial,
                    )

    assert final.policy_verdict != PolicyVerdict.PASS
    assert "empty alternative pool" in (final.message or "").lower()
    assert len(history) >= 1
