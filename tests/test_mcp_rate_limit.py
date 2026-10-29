"""MCP evaluate/repair share live caps; list_presets stays unlimited."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings, get_settings
from app.mcp_server import (
    tasteguard_evaluate,
    tasteguard_list_presets,
)
from app.rate_limit import (
    LiveCapExceeded,
    consume_live_call,
    enforce_mcp_rate_limit,
    reset_for_tests,
)

# Confirm @mcp.tool() returns the original coroutine (FastMCP decorator).
assert asyncio.iscoroutinefunction(tasteguard_evaluate)


def setup_function() -> None:
    reset_for_tests()
    get_settings.cache_clear()


def teardown_function() -> None:
    reset_for_tests()
    get_settings.cache_clear()


def test_mcp_minute_bucket_shared():
    get_settings.cache_clear()
    with patch(
        "app.rate_limit.get_settings",
        return_value=Settings(per_ip_minute_cap=1, daily_call_cap=500),
    ):
        enforce_mcp_rate_limit()
        with pytest.raises(LiveCapExceeded) as excinfo:
            enforce_mcp_rate_limit()
        assert excinfo.value.retry_after == 60
        assert "busy" in str(excinfo.value).lower()


def test_mcp_evaluate_respects_daily_cap_before_service():
    get_settings.cache_clear()
    with patch(
        "app.rate_limit.get_settings",
        return_value=Settings(per_ip_minute_cap=30, daily_call_cap=1),
    ):
        consume_live_call("203.0.113.9")
        mock_svc = MagicMock()
        mock_svc.evaluate = AsyncMock()
        with patch("app.mcp_server.TasteGuardService", return_value=mock_svc):
            with pytest.raises(LiveCapExceeded):
                asyncio.run(
                    tasteguard_evaluate(
                        city="Lisbon",
                        candidates=[{"name": "A Cevicheria"}],
                    )
                )
        mock_svc.evaluate.assert_not_called()


def test_list_presets_unlimited_after_caps_exhausted():
    get_settings.cache_clear()
    with patch(
        "app.rate_limit.get_settings",
        return_value=Settings(per_ip_minute_cap=1, daily_call_cap=1),
    ):
        enforce_mcp_rate_limit()
        with pytest.raises(LiveCapExceeded):
            enforce_mcp_rate_limit()
        presets = asyncio.run(tasteguard_list_presets())
        assert "presets" in presets
        assert len(presets["presets"]) >= 1
