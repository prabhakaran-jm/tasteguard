"""Best-effort in-process rate limits for live Qloo/Gemini endpoints.

Cloud Run: ``request.client.host`` is Google's front end, so every caller would
share one bucket. Use the first ``X-Forwarded-For`` hop, then fall back.

With ``max-instances=2``, each instance keeps its own counters — effective
ceiling is roughly 2× the configured per-IP / daily caps. Not a distributed
quota guarantee.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings

_lock = threading.Lock()
# key (client IP or MCP_BUCKET) -> timestamps of live calls in the rolling minute
_per_ip_minute: dict[str, deque[float]] = defaultdict(deque)
_day_key: str | None = None
_day_count: int = 0

BUSY_DETAIL = (
    "Live demo is busy — try the recorded run, or wait a minute and retry."
)

# MCP has no client IP, so all MCP callers share one minute bucket and the same
# daily cap as HTTP live calls.
MCP_BUCKET = "mcp:all"


class LiveCapExceeded(Exception):
    """Raised when a live call exceeds the per-key minute or daily cap."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = int(retry_after)
        super().__init__(BUSY_DETAIL)


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or ""
    if xff.strip():
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _roll_day(now: float) -> None:
    global _day_key, _day_count
    key = time.strftime("%Y-%m-%d", time.gmtime(now))
    if key != _day_key:
        _day_key = key
        _day_count = 0


def consume_live_call(key: str) -> None:
    """Record one live call against ``key``; raise LiveCapExceeded if over cap."""
    global _day_count
    settings = get_settings()
    minute_cap = max(1, int(settings.per_ip_minute_cap))
    daily_cap = max(1, int(settings.daily_call_cap))
    now = time.time()
    window_start = now - 60.0

    with _lock:
        _roll_day(now)
        bucket = _per_ip_minute[key]
        while bucket and bucket[0] < window_start:
            bucket.popleft()
        if len(bucket) >= minute_cap:
            raise LiveCapExceeded(60)
        if _day_count >= daily_cap:
            raise LiveCapExceeded(3600)
        bucket.append(now)
        _day_count += 1


def enforce_live_rate_limit(request: Request) -> None:
    """Call only for live propose / evaluate / repair (not recorded / health / presets).

    Default ~30 live HTTP calls per IP per minute (~10 full propose→evaluate→repair
    runs). Also enforces a process-local daily cap on live calls.
    """
    try:
        consume_live_call(client_ip(request))
    except LiveCapExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=BUSY_DETAIL,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


def enforce_mcp_rate_limit() -> None:
    """MCP has no client IP, so all MCP callers share one minute bucket and the same daily cap."""
    consume_live_call(MCP_BUCKET)


def reset_for_tests() -> None:
    """Clear counters between unit tests."""
    global _day_key, _day_count
    with _lock:
        _per_ip_minute.clear()
        _day_key = None
        _day_count = 0
