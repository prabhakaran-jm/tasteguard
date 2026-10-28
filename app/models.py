from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.geo import LatLng


class EvidenceState(str, Enum):
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    NO_CONFIDENT_MATCH = "no_confident_match"
    UNKNOWN = "unknown"


class EvaluationStatus(str, Enum):
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"


class PolicyVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class ItemVerdict(str, Enum):
    ALLOW = "allow"
    REWRITE = "rewrite"
    UNKNOWN = "unknown"


class CandidateInput(BaseModel):
    name: str
    neighbourhood: str | None = None
    address: str | None = None
    notes: str | None = None


class ScoredCandidate(BaseModel):
    input: CandidateInput
    evidence: EvidenceState
    item_verdict: ItemVerdict
    matched_name: str | None = None
    entity_id: str | None = None
    distance_km: float | None = None
    affinity: float | None = None
    anchor_percentile: float | None = None
    explainability: dict[str, float] = Field(default_factory=dict)
    explainability_summary: str | None = None
    category_ok: bool | None = None
    reasons: list[str] = Field(default_factory=list)
    kept_unverified: bool = False


class Alternative(BaseModel):
    entity_id: str
    name: str
    affinity: float | None = None
    distance_km: float | None = None
    address: str | None = None
    locality: str | None = None
    explainability_summary: str | None = None
    replacement_reason: str | None = None


class EvaluationResult(BaseModel):
    evaluation_status: EvaluationStatus
    policy_verdict: PolicyVerdict | None = None
    city: str
    candidates: list[ScoredCandidate]
    alternatives: list[Alternative] = Field(default_factory=list)
    anchor_count: int = 0
    message: str | None = None
    notes: dict[str, Any] = Field(default_factory=dict)


class EvaluateRequest(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    city: str
    city_center: LatLng
    seed_queries: list[dict[str, str]] = Field(default_factory=list)
    candidates: list[CandidateInput]
    fetch_alternatives: bool = True
