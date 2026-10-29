from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app import eval_cache
from app.config import get_settings
from app.gemini_agent import GeminiConcierge
from app.models import CandidateInput, EvaluateRequest, EvaluationResult
from app.presets import get_preset, inject_candidates, list_presets, preset_center
from app.public_pins import reject_http_client_pins
from app.rate_limit import enforce_live_rate_limit
from app.recorded import load_fixture
from app.service import TasteGuardService

router = APIRouter(prefix="/api")

MAX_CANDIDATES = 8
MAX_NAME_LEN = 120
MAX_ROUNDS = 3
Mode = Literal["live", "recorded"]


class ModeMixin(BaseModel):
    mode: Mode = "live"


class HealthResponse(BaseModel):
    qloo_key: bool
    gemini_key: bool


class ProposeRequest(BaseModel):
    preset_id: str = Field(..., min_length=1, max_length=80)
    # Client may force live even on a recorded preset (honest second button).
    force_live: bool = False


class ProposeResponse(ModeMixin):
    preset_id: str
    city: str
    persona: str
    candidates: list[CandidateInput]
    blurb: str | None = None
    captured_at: str | None = None


class EvaluateBody(BaseModel):
    preset_id: str = Field(..., min_length=1, max_length=80)
    candidates: list[CandidateInput] = Field(..., min_length=1, max_length=MAX_CANDIDATES)
    force_live: bool = False

    @field_validator("candidates")
    @classmethod
    def cap_candidates(cls, v: list[CandidateInput]) -> list[CandidateInput]:
        cleaned: list[CandidateInput] = []
        for c in v[:MAX_CANDIDATES]:
            name = (c.name or "").strip()
            if not name:
                continue
            cleaned.append(
                CandidateInput(
                    name=name[:MAX_NAME_LEN],
                    neighbourhood=_clip(c.neighbourhood, 80),
                    address=_clip(c.address, 160),
                    notes=_clip(c.notes, 200),
                    entity_id=_clip(c.entity_id, 80),
                    pinned_distance_km=c.pinned_distance_km,
                    pinned_locality=_clip(c.pinned_locality, 80),
                )
            )
        if not cleaned:
            raise ValueError("At least one candidate with a name is required")
        return cleaned


class EvaluateResponse(ModeMixin):
    evaluation_id: str
    result: EvaluationResult
    captured_at: str | None = None


class RepairBody(BaseModel):
    # Server rebuilds candidates from eval_cache — no client pin surface here.
    evaluation_id: str = Field(..., min_length=1, max_length=80)
    max_rounds: int = Field(default=MAX_ROUNDS, ge=0, le=MAX_ROUNDS)


class RepairResponse(ModeMixin):
    final: EvaluationResult
    history: list[EvaluationResult]


def _clip(value: str | None, n: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:n]


def _build_request(
    preset: dict[str, Any],
    candidates: list[CandidateInput],
    *,
    expected_count: int | None = None,
) -> EvaluateRequest:
    return EvaluateRequest(
        city=str(preset["city"]),
        city_center=preset_center(preset),
        seed_queries=list(preset.get("seed_queries") or []),
        candidates=candidates,
        fetch_alternatives=True,
        expected_count=expected_count,
    )


def _use_recorded(preset: dict[str, Any], force_live: bool) -> bool:
    return preset.get("kind") == "recorded" and not force_live


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        qloo_key=bool(settings.qloo_api_key),
        gemini_key=bool(settings.gemini_api_key),
    )


@router.get("/presets")
def presets() -> dict[str, Any]:
    return {
        "presets": list_presets(),
        "default_preset_id": "stress-lisbon-recorded",
        # Default preset is the recorded stress replay; live runs opt in explicitly.
        "mode": "recorded",
    }


@router.post("/propose", response_model=ProposeResponse)
async def propose(request: Request, body: ProposeRequest) -> ProposeResponse:
    preset = get_preset(body.preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Unknown preset_id")

    if preset.get("kind") == "recorded":
        fixture = load_fixture(str(preset["recorded_path"]))
        raw = fixture["propose"]["candidates"]
        candidates = [CandidateInput.model_validate(c) for c in raw][:MAX_CANDIDATES]
        captured = fixture.get("captured_at")
        captured_at = str(captured) if captured else None
        # force_live keeps the catch card but scores it with live Qloo.
        if body.force_live:
            enforce_live_rate_limit(request)
        return ProposeResponse(
            mode="live" if body.force_live else "recorded",
            preset_id=body.preset_id,
            city=str(preset["city"]),
            persona=str(preset["persona"]),
            candidates=candidates,
            blurb=preset.get("blurb"),
            captured_at=captured_at,
        )

    # Live paths (stress inject or Gemini) spend quota.
    enforce_live_rate_limit(request)

    if preset.get("kind") == "stress":
        candidates = inject_candidates(preset)[:MAX_CANDIDATES]
        return ProposeResponse(
            mode="live",
            preset_id=body.preset_id,
            city=str(preset["city"]),
            persona=str(preset["persona"]),
            candidates=candidates,
            blurb=preset.get("blurb"),
        )

    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not configured")
    agent = GeminiConcierge(settings)
    try:
        candidates = await agent.recommend(
            city=str(preset["city"]),
            persona_description=str(preset["persona"]),
            n=int(preset.get("n") or 5),
        )
    except Exception as exc:  # noqa: BLE001 — surface as error card, not PASS
        raise HTTPException(status_code=502, detail=f"Propose failed: {exc}") from exc

    capped = [
        CandidateInput(
            name=c.name[:MAX_NAME_LEN],
            neighbourhood=_clip(c.neighbourhood, 80),
            address=_clip(c.address, 160),
            notes=_clip(c.notes, 200),
        )
        for c in candidates[:MAX_CANDIDATES]
    ]
    return ProposeResponse(
        mode="live",
        preset_id=body.preset_id,
        city=str(preset["city"]),
        persona=str(preset["persona"]),
        candidates=capped,
        blurb=preset.get("blurb"),
    )


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(request: Request, body: EvaluateBody) -> EvaluateResponse:
    preset = get_preset(body.preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Unknown preset_id")

    # Null pin fields from /api/propose are OK; non-null pins are repair-only.
    reject_http_client_pins(body.candidates)

    if _use_recorded(preset, body.force_live):
        fixture = load_fixture(str(preset["recorded_path"]))
        result = EvaluationResult.model_validate(fixture["evaluate"])
        eval_request = _build_request(
            preset,
            body.candidates,
            expected_count=len(body.candidates),
        )
        eid = eval_cache.put(
            result,
            eval_request,
            persona_description=str(preset["persona"]),
        )
        # Tag so repair can short-circuit to fixture
        cached = eval_cache.get(eid)
        if cached:
            cached.result.notes = {
                **cached.result.notes,
                "recorded_path": preset["recorded_path"],
            }
        captured = fixture.get("captured_at")
        return EvaluateResponse(
            mode="recorded",
            evaluation_id=eid,
            result=result,
            captured_at=str(captured) if captured else None,
        )

    enforce_live_rate_limit(request)

    settings = get_settings()
    if not settings.qloo_api_key:
        raise HTTPException(status_code=503, detail="QLOO_API_KEY not configured")
    eval_request = _build_request(
        preset,
        body.candidates,
        expected_count=len(body.candidates),
    )
    try:
        result = await TasteGuardService(settings).evaluate(eval_request)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Evaluate failed: {exc}") from exc
    eid = eval_cache.put(
        result,
        eval_request,
        persona_description=str(preset["persona"]),
    )
    return EvaluateResponse(mode="live", evaluation_id=eid, result=result)


@router.post("/repair", response_model=RepairResponse)
async def repair(request: Request, body: RepairBody) -> RepairResponse:
    cached = eval_cache.get(body.evaluation_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="evaluation_id expired or unknown — run /evaluate again",
        )

    recorded_path = (cached.result.notes or {}).get("recorded_path")
    if recorded_path:
        fixture = load_fixture(str(recorded_path))
        final = EvaluationResult.model_validate(fixture["repair"]["final"])
        history = [cached.result, final]
        return RepairResponse(mode="recorded", final=final, history=history)

    enforce_live_rate_limit(request)

    rounds = int(body.max_rounds)  # already clamped by Field(le=MAX_ROUNDS)
    settings = get_settings()
    if not settings.qloo_api_key:
        raise HTTPException(status_code=503, detail="QLOO_API_KEY not configured")
    try:
        final, history = await TasteGuardService(settings).repair_until_pass(
            cached.request,
            persona_description=cached.persona_description,
            max_rounds=rounds,
            initial=cached.result,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Repair failed: {exc}") from exc
    return RepairResponse(mode="live", final=final, history=history)
