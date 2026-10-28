from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

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


def _clip_str(value: object, n: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:n]


class CandidateInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    neighbourhood: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=200)
    # When set (repair keep/replace), skip name search and trust this Qloo entity.
    entity_id: str | None = Field(default=None, max_length=80)
    pinned_distance_km: float | None = None
    pinned_locality: str | None = Field(default=None, max_length=80)

    @field_validator("name", mode="before")
    @classmethod
    def clip_name(cls, v: object) -> object:
        clipped = _clip_str(v, 120)
        return clipped if clipped is not None else v

    @field_validator("neighbourhood", mode="before")
    @classmethod
    def clip_neighbourhood(cls, v: object) -> str | None:
        return _clip_str(v, 80)

    @field_validator("address", mode="before")
    @classmethod
    def clip_address(cls, v: object) -> str | None:
        return _clip_str(v, 160)

    @field_validator("notes", mode="before")
    @classmethod
    def clip_notes(cls, v: object) -> str | None:
        return _clip_str(v, 200)


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
    candidates: list[CandidateInput] = Field(..., min_length=1, max_length=8)
    fetch_alternatives: bool = True
    # When set (repair), PASS requires this many candidates — shorter lists fail closed.
    expected_count: int | None = Field(default=None, ge=1, le=8)
    # Entity IDs already tried in prior repair rounds — excluded from the alt pool.
    exclude_entity_ids: list[str] = Field(default_factory=list)
