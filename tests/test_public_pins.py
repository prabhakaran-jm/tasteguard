"""HTTP rejects non-null client pins; null propose-shaped pins are accepted."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models import CandidateInput
from app.public_pins import PIN_REJECT_DETAIL, strip_mcp_client_pins


def test_http_evaluate_accepts_null_pin_fields():
    client = TestClient(app)
    # Propose-shaped payload (recorded fixture / UI round-trip).
    res = client.post(
        "/api/evaluate",
        json={
            "preset_id": "stress-lisbon-recorded",
            "force_live": False,
            "candidates": [
                {
                    "name": "A Cevicheria",
                    "neighbourhood": "Príncipe Real",
                    "address": None,
                    "notes": None,
                    "entity_id": None,
                    "pinned_distance_km": None,
                    "pinned_locality": None,
                }
            ],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["mode"] == "recorded"


def test_http_evaluate_rejects_non_null_entity_id():
    client = TestClient(app)
    res = client.post(
        "/api/evaluate",
        json={
            "preset_id": "stress-lisbon-recorded",
            "force_live": False,
            "candidates": [
                {
                    "name": "Fake Lisbon Name",
                    "entity_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                }
            ],
        },
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    text = detail if isinstance(detail, str) else str(detail)
    assert "names only" in text.lower() or PIN_REJECT_DETAIL in text


def test_mcp_strip_pins_names_affected():
    cands, ignored = strip_mcp_client_pins(
        [
            {
                "name": "A Cevicheria",
                "entity_id": "pin-1",
                "pinned_distance_km": 1.2,
            },
            {"name": "Plain Name"},
        ]
    )
    assert ignored == ["A Cevicheria"]
    assert cands[0].entity_id is None
    assert cands[0].pinned_distance_km is None
    assert isinstance(cands[0], CandidateInput)


def test_repair_body_has_no_candidate_surface():
    """ /api/repair only takes evaluation_id — no second pin bypass. """
    from app.api import RepairBody

    fields = set(RepairBody.model_fields)
    assert fields == {"evaluation_id", "max_rounds"}
