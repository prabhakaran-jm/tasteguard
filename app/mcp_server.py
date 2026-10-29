"""Thin FastMCP surface over TasteGuardService (official mcp.server.fastmcp).

Mounted at ``/mcp`` → SSE endpoint ``/mcp/sse`` for agent clients.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.geo import LatLng
from app.models import CandidateInput, EvaluateRequest, ItemVerdict
from app.presets import list_presets
from app.rate_limit import enforce_mcp_rate_limit
from app.service import TasteGuardService


def _transport_security() -> TransportSecuritySettings:
    """Cloud Run Host headers are not localhost — avoid 421 Invalid Host header.

    FastMCP defaults ``host=127.0.0.1``, which auto-enables DNS-rebinding
    protection with localhost-only allowlists. Behind Cloud Run that rejects
    ``*.run.app`` with HTTP 421. Prefer ``MCP_ALLOWED_HOSTS`` (comma-separated);
    otherwise disable rebinding checks (TLS + Cloud Run edge are the boundary).
    """
    local = [
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "testserver",
    ]
    raw = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
    if raw:
        hosts = [h.strip() for h in raw.split(",") if h.strip()] + local
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
        )
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


mcp = FastMCP(
    "TasteGuard",
    instructions=(
        "Cultural firewall for place agents. Evaluate restaurant lists against "
        "Qloo (resolve + taste affinity + explainability), then closed-set repair "
        "from a dinner alternative pool. PASS requires every slot ALLOW."
    ),
    transport_security=_transport_security(),
)


def _candidate_inputs(raw: list[dict[str, Any]]) -> list[CandidateInput]:
    out: list[CandidateInput] = []
    for item in raw[:8]:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        out.append(
            CandidateInput(
                name=name[:120],
                neighbourhood=(str(item["neighbourhood"])[:80] if item.get("neighbourhood") else None),
                address=(str(item["address"])[:160] if item.get("address") else None),
                notes=(str(item["notes"])[:200] if item.get("notes") else None),
                entity_id=(str(item["entity_id"])[:80] if item.get("entity_id") else None),
            )
        )
    if not out:
        raise ValueError("At least one candidate with a name is required")
    return out


def _summarize_result(result: Any) -> dict[str, Any]:
    cands = []
    for c in result.candidates:
        cands.append(
            {
                "name": c.input.name,
                "neighbourhood": c.input.neighbourhood,
                "verdict": c.item_verdict.value,
                "evidence": c.evidence.value,
                "matched_name": c.matched_name,
                "distance_km": c.distance_km,
                "affinity": c.affinity,
                "anchor_percentile": c.anchor_percentile,
                "explainability_summary": c.explainability_summary,
                "reasons": c.reasons[:4],
                "entity_id": c.entity_id,
            }
        )
    alts = [
        {
            "entity_id": a.entity_id,
            "name": a.name,
            "affinity": a.affinity,
            "distance_km": a.distance_km,
            "locality": a.locality,
            "replacement_reason": a.replacement_reason,
        }
        for a in (result.alternatives or [])[:12]
    ]
    return {
        "evaluation_status": result.evaluation_status.value,
        "policy_verdict": (
            result.policy_verdict.value if result.policy_verdict else None
        ),
        "city": result.city,
        "anchor_count": result.anchor_count,
        "message": result.message,
        "allow_count": sum(
            1 for c in result.candidates if c.item_verdict == ItemVerdict.ALLOW
        ),
        "candidates": cands,
        "alternatives": alts,
        "notes": {
            k: result.notes[k]
            for k in ("repair_round", "kept_allows", "replaced", "anchor_city")
            if k in (result.notes or {})
        },
    }


def _build_request(
    *,
    city: str,
    lat: float,
    lon: float,
    candidates: list[dict[str, Any]],
    seed_queries: list[dict[str, str]] | None,
) -> EvaluateRequest:
    return EvaluateRequest(
        city=city.strip(),
        city_center=LatLng(lat=float(lat), lon=float(lon)),
        seed_queries=list(seed_queries or []),
        candidates=_candidate_inputs(candidates),
        fetch_alternatives=True,
        expected_count=None,
    )


@mcp.tool()
async def tasteguard_list_presets() -> dict[str, Any]:
    """List TasteGuard demo presets (recorded / stress / live) and their cities."""
    return {"presets": list_presets()}


@mcp.tool()
async def tasteguard_evaluate(
    city: str,
    lat: float,
    lon: float,
    candidates: list[dict[str, Any]],
    seed_queries: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Evaluate a restaurant list with Qloo resolve + taste affinity.

    Each candidate is a dict with at least ``name``; optional ``neighbourhood``,
    ``address``, ``notes``, ``entity_id`` (pin skips name search).

    ``seed_queries`` items look like ``{\"query\": \"Radiohead\", \"types\": \"urn:entity:artist\"}``.

    Returns policy PASS/FAIL, per-item verdicts, and a closed dinner alternative
    pool when FAIL.
    """
    enforce_mcp_rate_limit()
    request = _build_request(
        city=city,
        lat=lat,
        lon=lon,
        candidates=candidates,
        seed_queries=seed_queries,
    )
    request.expected_count = len(request.candidates)
    result = await TasteGuardService().evaluate(request)
    return _summarize_result(result)


@mcp.tool()
async def tasteguard_repair(
    city: str,
    lat: float,
    lon: float,
    candidates: list[dict[str, Any]],
    seed_queries: list[dict[str, str]] | None = None,
    persona_description: str = "",
    max_rounds: int = 3,
) -> dict[str, Any]:
    """Evaluate then closed-set repair until PASS or rounds exhausted.

    Keeps ALLOW items; replaces rewrite/unknown slots from the Qloo dinner pool.
    Gemini may only pick pool entity IDs; invalid picks fall back to top affinity.
    """
    enforce_mcp_rate_limit()
    request = _build_request(
        city=city,
        lat=lat,
        lon=lon,
        candidates=candidates,
        seed_queries=seed_queries,
    )
    request.expected_count = len(request.candidates)
    rounds = max(0, min(int(max_rounds), 3))
    final, history = await TasteGuardService().repair_until_pass(
        request,
        persona_description=persona_description
        or f"Dinner recommendations in {city}",
        max_rounds=rounds,
    )
    summary = _summarize_result(final)
    summary["history_len"] = len(history)
    summary["rounds_attempted"] = max(0, len(history) - 1)
    return summary


def mcp_sse_app():
    """ASGI app with /sse and /messages — mount under ``/mcp``."""
    return mcp.sse_app()
