"""Public-boundary handling for client-supplied entity pins.

Internal repair may set entity_id / pinned_* on CandidateInput. External HTTP
and MCP callers must not use those fields to skip name/geo/category checks.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.models import CandidateInput

PIN_REJECT_DETAIL = (
    "entity_id and pinned_* are set by TasteGuard during repair; send names only."
)


def candidate_has_non_null_pin(candidate: CandidateInput | dict[str, Any]) -> bool:
    if isinstance(candidate, CandidateInput):
        return (
            candidate.entity_id is not None
            or candidate.pinned_distance_km is not None
            or candidate.pinned_locality is not None
        )
    return (
        candidate.get("entity_id") is not None
        or candidate.get("pinned_distance_km") is not None
        or candidate.get("pinned_locality") is not None
    )


def reject_http_client_pins(candidates: list[CandidateInput]) -> None:
    """HTTP evaluate: 422 if any pin field is non-null. Null keys from propose are OK."""
    if any(candidate_has_non_null_pin(c) for c in candidates):
        raise HTTPException(status_code=422, detail=PIN_REJECT_DETAIL)


def strip_mcp_client_pins(
    raw: list[dict[str, Any]],
) -> tuple[list[CandidateInput], list[str]]:
    """MCP: drop non-null pins and resolve by name. Return (candidates, ignored names)."""
    out: list[CandidateInput] = []
    ignored: list[str] = []
    for item in raw[:8]:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if candidate_has_non_null_pin(item):
            ignored.append(name[:120])
        out.append(
            CandidateInput(
                name=name[:120],
                neighbourhood=(
                    str(item["neighbourhood"])[:80] if item.get("neighbourhood") else None
                ),
                address=(str(item["address"])[:160] if item.get("address") else None),
                notes=(str(item["notes"])[:200] if item.get("notes") else None),
                entity_id=None,
                pinned_distance_km=None,
                pinned_locality=None,
            )
        )
    if not out:
        raise ValueError("At least one candidate with a name is required")
    return out, ignored
