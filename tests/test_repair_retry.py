"""Selective repair retry: transient upstream only; logs + safe 502 body."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import REPAIR_UNAVAILABLE, _is_retryable_repair_error
from app.eval_cache import put
from app.geo import LatLng
from app.main import app
from app.models import (
    CandidateInput,
    EvaluateRequest,
    EvaluationResult,
    EvaluationStatus,
    EvidenceState,
    ItemVerdict,
    PolicyVerdict,
    ScoredCandidate,
)
from app.qloo_client import QlooError


def test_retryable_qloo_429_and_5xx():
    assert _is_retryable_repair_error(QlooError("rate", status_code=429))
    assert _is_retryable_repair_error(QlooError("boom", status_code=503))
    assert not _is_retryable_repair_error(QlooError("bad", status_code=400))


def test_retryable_timeouts_not_value_error():
    assert _is_retryable_repair_error(httpx.ReadTimeout("slow"))
    assert not _is_retryable_repair_error(ValueError("empty pool logic"))
    assert not _is_retryable_repair_error(KeyError("x"))


def _fail_cached() -> str:
    request = EvaluateRequest(
        city="Lisbon",
        city_center=LatLng(lat=38.72, lon=-9.14),
        seed_queries=[],
        candidates=[CandidateInput(name="A")],
        expected_count=1,
    )
    result = EvaluationResult(
        evaluation_status=EvaluationStatus.COMPLETED,
        policy_verdict=PolicyVerdict.FAIL,
        city="Lisbon",
        candidates=[
            ScoredCandidate(
                input=CandidateInput(name="A"),
                evidence=EvidenceState.MISMATCH,
                item_verdict=ItemVerdict.REWRITE,
                reasons=["test"],
            )
        ],
        alternatives=[],
        anchor_count=1,
        message="FAIL",
        notes={},
    )
    return put(result, request, persona_description="test")


def test_repair_retries_once_on_qloo_429_then_succeeds():
    eid = _fail_cached()
    ok = EvaluationResult(
        evaluation_status=EvaluationStatus.COMPLETED,
        policy_verdict=PolicyVerdict.PASS,
        city="Lisbon",
        candidates=[
            ScoredCandidate(
                input=CandidateInput(name="A"),
                evidence=EvidenceState.VERIFIED,
                item_verdict=ItemVerdict.ALLOW,
                reasons=[],
            )
        ],
        alternatives=[],
        anchor_count=1,
        message="PASS",
        notes={},
    )
    mock_svc = MagicMock()
    mock_svc.repair_until_pass = AsyncMock(
        side_effect=[QlooError("rate", status_code=429), (ok, [ok])]
    )
    client = TestClient(app)
    with patch("app.api.TasteGuardService", return_value=mock_svc):
        with patch("app.api.enforce_live_rate_limit"):
            res = client.post("/api/repair", json={"evaluation_id": eid})
    assert res.status_code == 200, res.text
    assert mock_svc.repair_until_pass.await_count == 2
    assert res.json()["final"]["policy_verdict"] == "PASS"


def test_repair_does_not_retry_programming_error():
    eid = _fail_cached()
    mock_svc = MagicMock()
    mock_svc.repair_until_pass = AsyncMock(side_effect=KeyError("bug"))
    client = TestClient(app)
    with patch("app.api.TasteGuardService", return_value=mock_svc):
        with patch("app.api.enforce_live_rate_limit"):
            res = client.post("/api/repair", json={"evaluation_id": eid})
    assert res.status_code == 502
    assert res.json()["detail"] == REPAIR_UNAVAILABLE
    assert mock_svc.repair_until_pass.await_count == 1
