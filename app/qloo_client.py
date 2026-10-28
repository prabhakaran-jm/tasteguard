from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class QlooError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class QlooClient:
    """Async Qloo hackathon API client.

    Search uses ``types=`` (not ``filter.type``).
    ``filter.location`` on Search must be ``lat,lon`` (not a city name).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.settings = settings or get_settings()
        self._client = client
        self._owned_client = client is None

    async def __aenter__(self) -> "QlooClient":
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.qloo_base_url.rstrip("/"),
                headers={"X-Api-Key": self.settings.qloo_api_key},
                timeout=self.settings.http_timeout_seconds,
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owned_client and self._client is not None:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("QlooClient must be used as an async context manager")
        return self._client

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.qloo_api_key:
            raise QlooError("QLOO_API_KEY is not configured", status_code=401)

        flat: list[tuple[str, str]] = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                flat.append((key, ",".join(str(v) for v in value)))
            elif isinstance(value, bool):
                flat.append((key, "true" if value else "false"))
            else:
                flat.append((key, str(value)))

        last_exc: Exception | None = None
        for attempt in range(self.settings.http_retries + 1):
            try:
                resp = await self.client.get(path, params=flat)
                if resp.status_code >= 500:
                    raise QlooError(
                        f"Qloo {resp.status_code}: {resp.text[:300]}",
                        resp.status_code,
                    )
                if resp.status_code == 429:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                if resp.status_code >= 400:
                    raise QlooError(
                        f"Qloo {resp.status_code}: {resp.text[:500]}",
                        resp.status_code,
                    )
                return resp.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                await asyncio.sleep(0.3 * (attempt + 1))
        raise QlooError(f"Qloo request failed after retries: {last_exc}")

    async def search(
        self,
        query: str,
        types: str = "urn:entity:place",
        *,
        filter_location_latlon: str | None = None,
        filter_radius_miles: float | None = None,
        take: int = 8,
    ) -> list[dict[str, Any]]:
        """Entity search.

        ``filter_location_latlon`` must look like ``38.7223,-9.1393`` when set.
        Do not pass a city name to ``filter.location``.
        """
        params: dict[str, Any] = {
            "query": query,
            "types": types,
            "take": take,
        }
        if filter_location_latlon:
            params["filter.location"] = filter_location_latlon
        if filter_radius_miles is not None:
            params["filter.radius"] = filter_radius_miles
        data = await self._get("/search", params)
        if isinstance(data.get("results"), list):
            return data["results"]
        results = data.get("results") or {}
        if isinstance(results, dict):
            return list(results.get("entities") or results.get("places") or [])
        return []

    async def insights(
        self,
        *,
        filter_type: str = "urn:entity:place",
        signal_interest_entities: list[str] | None = None,
        signal_interest_tags: list[str] | None = None,
        filter_results_entities: list[str] | None = None,
        filter_exclude_entities: list[str] | None = None,
        filter_location_query: str | None = None,
        filter_location_radius: float | None = None,
        filter_popularity_min: float | None = None,
        filter_popularity_max: float | None = None,
        feature_explainability: bool = True,
        take: int = 20,
        page: int = 1,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "filter.type": filter_type,
            "take": min(max(take, 1), 50),
            "page": min(max(page, 1), 100),
            "feature.explainability": feature_explainability,
        }
        if signal_interest_entities:
            params["signal.interests.entities"] = signal_interest_entities
        if signal_interest_tags:
            params["signal.interests.tags"] = signal_interest_tags
        if filter_results_entities:
            params["filter.results.entities"] = filter_results_entities
        if filter_exclude_entities:
            params["filter.exclude.entities"] = filter_exclude_entities
        if filter_location_query:
            params["filter.location.query"] = filter_location_query
        if filter_location_radius is not None:
            params["filter.location.radius"] = filter_location_radius
        if filter_popularity_min is not None:
            params["filter.popularity.min"] = filter_popularity_min
        if filter_popularity_max is not None:
            params["filter.popularity.max"] = filter_popularity_max
        return await self._get("/v2/insights", params)

    async def tags(self, query: str, take: int = 10) -> list[dict[str, Any]]:
        data = await self._get("/v2/tags", {"filter.query": query, "take": take})
        results = data.get("results") or {}
        if isinstance(results, dict):
            return list(results.get("tags") or [])
        if isinstance(results, list):
            return results
        return []


def entities_from_insights(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results") or {}
    if isinstance(results, dict):
        return list(results.get("entities") or [])
    if isinstance(results, list):
        return results
    return []


def affinity_of(entity: dict[str, Any]) -> float | None:
    query = entity.get("query") or {}
    if isinstance(query, dict) and "affinity" in query:
        try:
            return float(query["affinity"])
        except (TypeError, ValueError):
            return None
    if "affinity" in entity:
        try:
            return float(entity["affinity"])
        except (TypeError, ValueError):
            return None
    return None


def explainability_of(entity: dict[str, Any]) -> dict[str, float]:
    query = entity.get("query") or {}
    block = None
    if isinstance(query, dict):
        block = query.get("explainability")
    if block is None:
        block = entity.get("explainability")
    out: dict[str, float] = {}
    if not isinstance(block, dict):
        return out
    interests = block.get("signal.interests.entities") or block.get("entities") or block
    if isinstance(interests, dict):
        for key, val in interests.items():
            try:
                out[str(key)] = float(val)
            except (TypeError, ValueError):
                continue
    return out


def extract_latlng(entity: dict[str, Any]) -> dict[str, float] | None:
    props = entity.get("properties") or {}
    loc = entity.get("location") or props.get("location") or {}
    for container in (loc, props, entity):
        if not isinstance(container, dict):
            continue
        for lat_k, lon_k in (("lat", "lon"), ("latitude", "longitude"), ("lat", "lng")):
            if lat_k in container and lon_k in container:
                try:
                    return {
                        "lat": float(container[lat_k]),
                        "lon": float(container[lon_k]),
                    }
                except (TypeError, ValueError):
                    pass
        geocode = container.get("geocode")
        if isinstance(geocode, dict) and "lat" in geocode:
            try:
                return {
                    "lat": float(geocode["lat"]),
                    "lon": float(geocode.get("lon", geocode.get("lng"))),
                }
            except (TypeError, ValueError):
                pass
    return None


def extract_address(entity: dict[str, Any]) -> str | None:
    props = entity.get("properties") or {}
    for key in ("address", "formatted_address", "street_address"):
        val = props.get(key) or entity.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None
