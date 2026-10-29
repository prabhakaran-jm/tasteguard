"""Live endpoints rate-limit; recorded / health / presets stay unlimited."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Settings, get_settings
from app.main import app
from app.rate_limit import reset_for_tests


def setup_function() -> None:
    reset_for_tests()
    get_settings.cache_clear()


def teardown_function() -> None:
    reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.skipif(
    not (ROOT / "recorded/stress-lisbon.json").is_file(),
    reason="recorded fixture is private",
)
def test_recorded_propose_never_rate_limited():
    get_settings.cache_clear()
    with patch(
        "app.rate_limit.get_settings",
        return_value=Settings(per_ip_minute_cap=2, daily_call_cap=500),
    ):
        client = TestClient(app)
        for _ in range(6):
            res = client.post(
                "/api/propose",
                json={"preset_id": "stress-lisbon-recorded", "force_live": False},
            )
            assert res.status_code == 200, res.text
            assert res.json()["mode"] == "recorded"


def test_missing_recorded_fixture_returns_503(tmp_path: Path):
    get_settings.cache_clear()
    with patch("app.recorded.ROOT", tmp_path):
        client = TestClient(app)
        res = client.post(
            "/api/propose",
            json={"preset_id": "stress-lisbon-recorded", "force_live": False},
        )
    assert res.status_code == 503
    assert "live preset" in res.json()["detail"].lower()


def test_live_stress_hits_429_after_minute_cap():
    get_settings.cache_clear()
    with patch(
        "app.rate_limit.get_settings",
        return_value=Settings(per_ip_minute_cap=10, daily_call_cap=500),
    ):
        client = TestClient(app)
        headers = {"X-Forwarded-For": "203.0.113.50"}
        for i in range(10):
            res = client.post(
                "/api/propose",
                json={"preset_id": "stress-lisbon-live", "force_live": False},
                headers=headers,
            )
            assert res.status_code == 200, f"call {i + 1}: {res.text}"
        res = client.post(
            "/api/propose",
            json={"preset_id": "stress-lisbon-live", "force_live": False},
            headers=headers,
        )
        assert res.status_code == 429
        assert "recorded" in res.json()["detail"].lower()
        assert res.headers.get("retry-after") == "60"


def test_health_and_presets_unlimited():
    get_settings.cache_clear()
    with patch(
        "app.rate_limit.get_settings",
        return_value=Settings(per_ip_minute_cap=1, daily_call_cap=1),
    ):
        client = TestClient(app)
        for _ in range(5):
            assert client.get("/api/health").status_code == 200
            assert client.get("/api/presets").status_code == 200


def test_xff_first_hop_keys_bucket():
    get_settings.cache_clear()
    with patch(
        "app.rate_limit.get_settings",
        return_value=Settings(per_ip_minute_cap=1, daily_call_cap=500),
    ):
        client = TestClient(app)
        a = client.post(
            "/api/propose",
            json={"preset_id": "stress-lisbon-live"},
            headers={"X-Forwarded-For": "198.51.100.1, 10.0.0.1"},
        )
        assert a.status_code == 200
        blocked = client.post(
            "/api/propose",
            json={"preset_id": "stress-lisbon-live"},
            headers={"X-Forwarded-For": "198.51.100.1, 10.0.0.1"},
        )
        assert blocked.status_code == 429
        other = client.post(
            "/api/propose",
            json={"preset_id": "stress-lisbon-live"},
            headers={"X-Forwarded-For": "198.51.100.2"},
        )
        assert other.status_code == 200
