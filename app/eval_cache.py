"""Short-lived in-memory cache so /repair starts from the FAIL the judge saw."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass

from app.models import EvaluateRequest, EvaluationResult

TTL_SECONDS = 300


@dataclass
class CachedEvaluation:
    result: EvaluationResult
    request: EvaluateRequest
    persona_description: str
    expires_at: float


_lock = threading.Lock()
_store: dict[str, CachedEvaluation] = {}


def put(
    result: EvaluationResult,
    request: EvaluateRequest,
    persona_description: str,
    *,
    ttl: float = TTL_SECONDS,
) -> str:
    eid = uuid.uuid4().hex
    with _lock:
        _purge_locked()
        _store[eid] = CachedEvaluation(
            result=result,
            request=request,
            persona_description=persona_description,
            expires_at=time.monotonic() + ttl,
        )
    return eid


def get(evaluation_id: str) -> CachedEvaluation | None:
    with _lock:
        _purge_locked()
        return _store.get(evaluation_id)


def _purge_locked() -> None:
    now = time.monotonic()
    dead = [k for k, v in _store.items() if v.expires_at <= now]
    for k in dead:
        del _store[k]
