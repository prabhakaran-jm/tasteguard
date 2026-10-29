"""MCP coordinate defaults and seed validation (offline)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp_coords import resolve_mcp_coords
from app.mcp_seeds import validate_mcp_seed_queries
from app.mcp_server import tasteguard_evaluate, tasteguard_list_presets
from app.rate_limit import reset_for_tests
from app.config import get_settings


def setup_function() -> None:
    reset_for_tests()
    get_settings.cache_clear()


def teardown_function() -> None:
    reset_for_tests()
    get_settings.cache_clear()


def test_lisbon_defaults_coords():
    lat, lon = resolve_mcp_coords("Lisbon", None, None)
    assert lat == pytest.approx(38.7223)
    assert lon == pytest.approx(-9.1393)


def test_unknown_city_requires_coords():
    with pytest.raises(ValueError, match="Unknown city"):
        resolve_mcp_coords("Paris", None, None)


def test_seed_requires_types_not_type():
    with pytest.raises(ValueError, match="types"):
        validate_mcp_seed_queries([{"query": "Radiohead", "type": "artist"}])


def test_seed_accepts_documented_shape():
    out = validate_mcp_seed_queries(
        [{"query": "Radiohead", "types": "urn:entity:artist"}]
    )
    assert out == [{"query": "Radiohead", "types": "urn:entity:artist"}]


def test_list_presets_unaffected_by_input_helpers():
    data = asyncio.run(tasteguard_list_presets())
    assert len(data["presets"]) >= 4


def test_evaluate_strips_pins_and_notes_names():
    mock_result = MagicMock()
    mock_result.evaluation_status.value = "completed"
    mock_result.policy_verdict.value = "FAIL"
    mock_result.city = "Lisbon"
    mock_result.anchor_count = 0
    mock_result.message = "fail"
    mock_result.candidates = []
    mock_result.alternatives = []
    mock_result.notes = {}

    mock_svc = MagicMock()
    mock_svc.evaluate = AsyncMock(return_value=mock_result)

    with patch("app.mcp_server.TasteGuardService", return_value=mock_svc):
        with patch("app.mcp_server.enforce_mcp_rate_limit"):
            summary = asyncio.run(
                tasteguard_evaluate(
                    city="Lisbon",
                    candidates=[
                        {
                            "name": "Le Comptoir du Relais",
                            "entity_id": "paris-pin",
                            "neighbourhood": "Chiado",
                        }
                    ],
                )
            )

    req = mock_svc.evaluate.await_args.args[0]
    assert req.candidates[0].entity_id is None
    assert req.city_center.lat == pytest.approx(38.7223)
    assert summary["notes"]["client_pins_ignored"] == ["Le Comptoir du Relais"]
