from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.category import is_restaurant_like, tag_names
from app.config import Settings, get_settings
from app.geo import LatLng, extract_address, extract_latlng, extract_locality, haversine_km, latlon_param
from app.models import CandidateInput, EvidenceState
from app.names import name_similarity
from app.qloo_client import QlooClient

logger = logging.getLogger(__name__)


@dataclass
class PlaceEntity:
    entity_id: str
    name: str
    location: LatLng | None = None
    address: str | None = None
    locality: str | None = None
    tags: list[str] = field(default_factory=list)
    is_restaurant: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolveHit:
    evidence: EvidenceState
    entity: PlaceEntity | None = None
    distance_km: float | None = None
    similarity: float | None = None
    reasons: list[str] = field(default_factory=list)


def _to_place(entity: dict[str, Any]) -> PlaceEntity:
    eid = str(entity.get("entity_id") or entity.get("id") or "")
    return PlaceEntity(
        entity_id=eid,
        name=str(entity.get("name") or ""),
        location=extract_latlng(entity),
        address=extract_address(entity),
        locality=extract_locality(entity),
        tags=tag_names(entity),
        is_restaurant=is_restaurant_like(entity),
        raw=entity,
    )


class PlaceResolver:
    """Two-stage place resolver with in-city-first chain handling.

    1. Search locally (lat,lon + radius) and broadly (global).
    2. If any name-passing hit is within near radius → verified (or mismatch if not restaurant).
    3. Mismatch only when no in-city match exists and a confident match exists elsewhere.
    """

    def __init__(self, qloo: QlooClient, settings: Settings | None = None):
        self.qloo = qloo
        self.settings = settings or get_settings()
        self._sem = asyncio.Semaphore(self.settings.search_concurrency)

    async def resolve(
        self,
        candidate: CandidateInput,
        *,
        city_label: str,
        city_center: LatLng,
    ) -> ResolveHit:
        radius_miles = max(self.settings.near_radius_km / 1.609, 5.0)
        async with self._sem:
            local = await self.qloo.search(
                candidate.name,
                types="urn:entity:place",
                filter_location_latlon=latlon_param(city_center),
                filter_radius_miles=radius_miles,
                take=8,
            )
            broad = await self.qloo.search(
                candidate.name,
                types="urn:entity:place",
                take=8,
            )

        local_hits = self._rank_hits(local, candidate.name, city_center)
        broad_hits = self._rank_hits(broad, candidate.name, city_center)

        # In-city-first: any name-passing hit within near radius → Verified
        for place, sim, dist in local_hits + broad_hits:
            if dist is None:
                continue
            if sim < self.settings.name_similarity_threshold:
                continue
            if dist <= self.settings.near_radius_km:
                if place.is_restaurant is False:
                    return ResolveHit(
                        evidence=EvidenceState.MISMATCH,
                        entity=place,
                        distance_km=dist,
                        similarity=sim,
                        reasons=[
                            f"Matched '{place.name}' within {dist:.1f} km of {city_label} "
                            "but category is not restaurant-like",
                        ],
                    )
                return ResolveHit(
                    evidence=EvidenceState.VERIFIED,
                    entity=place,
                    distance_km=dist,
                    similarity=sim,
                    reasons=[
                        f"Matched Qloo place '{place.name}' "
                        f"({dist:.1f} km from {city_label})"
                    ],
                )

        # Mismatch: confident match elsewhere, none in-city
        remote = [
            (p, s, d)
            for p, s, d in broad_hits
            if s >= self.settings.name_similarity_threshold
            and d is not None
            and d > self.settings.near_radius_km
        ]
        if remote:
            place, sim, dist = remote[0]
            neighbourhood = candidate.neighbourhood or candidate.address or "unspecified"
            return ResolveHit(
                evidence=EvidenceState.MISMATCH,
                entity=place,
                distance_km=dist,
                similarity=sim,
                reasons=[
                    f"Gemini said {neighbourhood} / {city_label}; Qloo places "
                    f"'{place.name}' {dist:.1f} km away "
                    f"({place.locality or place.address or 'unknown locality'})",
                    "No in-city name match found",
                ],
            )

        if broad_hits or local_hits:
            best = (local_hits or broad_hits)[0]
            return ResolveHit(
                evidence=EvidenceState.UNKNOWN,
                entity=best[0],
                distance_km=best[2],
                similarity=best[1],
                reasons=[
                    f"Ambiguous match '{best[0].name}' "
                    f"(similarity {best[1]:.2f}); below threshold or missing geo"
                ],
            )

        return ResolveHit(
            evidence=EvidenceState.NO_CONFIDENT_MATCH,
            reasons=["No confident Qloo match found"],
        )

    def _rank_hits(
        self,
        raw: list[dict[str, Any]],
        query_name: str,
        city_center: LatLng,
    ) -> list[tuple[PlaceEntity, float, float | None]]:
        ranked: list[tuple[PlaceEntity, float, float | None]] = []
        seen: set[str] = set()
        for entity in raw:
            place = _to_place(entity)
            if not place.entity_id or place.entity_id in seen:
                continue
            seen.add(place.entity_id)
            sim = name_similarity(query_name, place.name)
            dist = (
                haversine_km(city_center, place.location)
                if place.location is not None
                else None
            )
            ranked.append((place, sim, dist))
        ranked.sort(key=lambda t: (-t[1], t[2] if t[2] is not None else 1e9))
        return ranked
