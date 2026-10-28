from __future__ import annotations

import logging
from typing import Any

from app.category import is_restaurant_like
from app.config import Settings, get_settings
from app.geo import LatLng, extract_address, extract_latlng, extract_locality, haversine_km
from app.models import (
    Alternative,
    EvaluationStatus,
    EvidenceState,
    ItemVerdict,
)
from app.qloo_client import (
    QlooClient,
    QlooError,
    affinity_of,
    entities_from_insights,
    explainability_of,
)
from app.resolver import PlaceEntity, ResolveHit

logger = logging.getLogger(__name__)

# Probe: sent 40 IDs, got 30 back — keep shared-pool requests within this budget.
MAX_FILTER_RESULTS_IDS = 30

# Stable per-city restaurant anchor IDs (filled on first successful build).
_ANCHOR_ID_CACHE: dict[str, list[str]] = {}


def summarize_explainability(
    contrib: dict[str, float],
    id_to_label: dict[str, str] | None = None,
) -> str | None:
    if not contrib:
        return "Explanation unavailable"
    labels = id_to_label or {}
    top = sorted(contrib.items(), key=lambda kv: kv[1], reverse=True)[0]
    label = labels.get(top[0], top[0])
    return f"Strongest contributing interest: {label} ({top[1]:.2f})"


class AnchorScorer:
    """Score candidates with a fixed in-city restaurant anchor set in one Insights call."""

    def __init__(self, qloo: QlooClient, settings: Settings | None = None):
        self.qloo = qloo
        self.settings = settings or get_settings()

    async def build_anchors(
        self,
        *,
        city: str,
        city_center: LatLng,
        signal_entities: list[str] | None = None,
    ) -> list[PlaceEntity]:
        """Build a mid/high-popularity in-city restaurant sample.

        Intentionally does **not** pass persona signals — otherwise Insights
        returns the high-affinity tail and every real Gemini pick scores pct=0.
        Persona signals are applied later in ``score_shared_pool``.

        Anchor entity IDs are cached per city so relative percentiles stay stable
        across runs in the same process.
        """
        _ = signal_entities  # kept for call-site compatibility
        cache_key = city.strip().casefold()
        cached = _ANCHOR_ID_CACHE.get(cache_key)
        if cached and len(cached) >= self.settings.anchor_floor:
            return [
                PlaceEntity(
                    entity_id=eid,
                    name="",
                    location=None,
                    is_restaurant=True,
                )
                for eid in cached
            ]

        anchors: list[PlaceEntity] = []
        seen: set[str] = set()
        # Broader popularity bands + more pages to survive strict restaurant filter
        bands = (
            (0.50, 0.95, 1),
            (0.50, 0.95, 2),
            (0.35, 0.80, 1),
            (0.35, 0.80, 2),
            (0.20, 0.70, 1),
            (0.20, 0.70, 2),
        )
        for pop_min, pop_max, page in bands:
            if len(anchors) >= self.settings.anchor_target:
                break
            try:
                payload = await self.qloo.insights(
                    filter_type="urn:entity:place",
                    # No signal.interests.entities here (popularity sample only).
                    filter_location_query=city,
                    filter_popularity_min=pop_min,
                    filter_popularity_max=pop_max,
                    feature_explainability=False,
                    take=50,
                    page=page,
                )
            except QlooError as exc:
                logger.warning("anchor fetch failed: %s", exc)
                continue
            for raw in entities_from_insights(payload):
                place = self._restaurant_near(raw, city_center, seen)
                if place is None:
                    continue
                anchors.append(place)
                if len(anchors) >= self.settings.anchor_target:
                    break
        if len(anchors) < self.settings.anchor_floor:
            # Fallback: local search for restaurants (still no persona bias)
            try:
                from app.geo import latlon_param

                hits = await self.qloo.search(
                    "restaurant",
                    types="urn:entity:place",
                    filter_location_latlon=latlon_param(city_center),
                    filter_radius_miles=max(self.settings.near_radius_km / 1.609, 5.0),
                    take=50,
                )
                for raw in hits:
                    place = self._restaurant_near(raw, city_center, seen)
                    if place is None:
                        continue
                    anchors.append(place)
                    if len(anchors) >= self.settings.anchor_target:
                        break
            except QlooError as exc:
                logger.warning("anchor search fallback failed: %s", exc)
        if len(anchors) >= self.settings.anchor_floor:
            _ANCHOR_ID_CACHE[cache_key] = [a.entity_id for a in anchors]
        return anchors

    def _restaurant_near(
        self,
        raw: dict[str, Any],
        city_center: LatLng,
        seen: set[str],
    ) -> PlaceEntity | None:
        if not is_restaurant_like(raw):
            return None
        eid = str(raw.get("entity_id") or raw.get("id") or "")
        if not eid or eid in seen:
            return None
        loc = extract_latlng(raw)
        if loc is None:
            return None
        dist = haversine_km(city_center, loc)
        if dist > self.settings.near_radius_km:
            return None
        seen.add(eid)
        return PlaceEntity(
            entity_id=eid,
            name=str(raw.get("name") or ""),
            location=loc,
            address=extract_address(raw),
            locality=extract_locality(raw),
            is_restaurant=True,
            raw=raw,
        )

    async def score_shared_pool(
        self,
        *,
        signal_entities: list[str],
        candidate_ids: list[str],
        anchor_ids: list[str],
        id_labels: dict[str, str] | None = None,
    ) -> tuple[EvaluationStatus, dict[str, dict[str, Any]], str | None]:
        # Candidates first, then anchors, capped at MAX_FILTER_RESULTS_IDS
        pool: list[str] = []
        for eid in list(dict.fromkeys(candidate_ids)) + list(dict.fromkeys(anchor_ids)):
            if eid not in pool:
                pool.append(eid)
            if len(pool) >= MAX_FILTER_RESULTS_IDS:
                break

        if not pool:
            return EvaluationStatus.PARTIAL, {}, "No entity IDs to score"

        try:
            payload = await self.qloo.insights(
                filter_type="urn:entity:place",
                signal_interest_entities=signal_entities or None,
                filter_results_entities=pool,
                feature_explainability=True,
                take=min(50, max(len(pool), 1)),
            )
        except QlooError as exc:
            return EvaluationStatus.UNAVAILABLE, {}, f"Qloo unavailable: {exc}"

        by_id: dict[str, dict[str, Any]] = {}
        for raw in entities_from_insights(payload):
            eid = str(raw.get("entity_id") or raw.get("id") or "")
            if eid not in pool:
                continue  # drop backfill extras
            by_id[eid] = {
                "affinity": affinity_of(raw),
                "explainability": explainability_of(raw),
                "raw": raw,
                "summary": summarize_explainability(
                    explainability_of(raw), id_labels
                ),
            }

        scored_anchor_ids = [
            a
            for a in anchor_ids
            if a in by_id and by_id[a]["affinity"] is not None
        ]
        if len(scored_anchor_ids) < self.settings.anchor_floor:
            return (
                EvaluationStatus.PARTIAL,
                by_id,
                f"Insufficient anchors with affinity "
                f"({len(scored_anchor_ids)} < {self.settings.anchor_floor}); "
                "affinity shown as informational only — never PASS",
            )
        return EvaluationStatus.COMPLETED, by_id, None

    def relative_percentile(
        self,
        candidate_affinity: float,
        anchor_affinities: list[float],
    ) -> float:
        if not anchor_affinities:
            return 0.0
        beats = sum(1 for a in anchor_affinities if candidate_affinity >= a)
        return beats / len(anchor_affinities)

    def item_from_resolve_and_score(
        self,
        *,
        hit: ResolveHit,
        scored: dict[str, Any] | None,
        anchor_affinities: list[float],
        evaluation_status: EvaluationStatus,
    ) -> tuple[ItemVerdict, float | None, float | None, list[str]]:
        reasons = list(hit.reasons)
        affinity = scored["affinity"] if scored else None
        percentile = None

        if hit.evidence == EvidenceState.MISMATCH:
            return ItemVerdict.REWRITE, affinity, None, reasons

        if hit.evidence in (
            EvidenceState.NO_CONFIDENT_MATCH,
            EvidenceState.UNKNOWN,
        ):
            return ItemVerdict.UNKNOWN, None, None, reasons

        # verified
        if evaluation_status != EvaluationStatus.COMPLETED:
            reasons.append("Evaluation not completed — informational only")
            return ItemVerdict.UNKNOWN, affinity, None, reasons
        if affinity is None:
            reasons.append("Qloo returned no taste score — unscored")
            return ItemVerdict.UNKNOWN, None, None, reasons

        percentile = self.relative_percentile(affinity, anchor_affinities)
        cutoff = self.settings.allow_anchor_percentile
        band = self.settings.allow_borderline_band
        if percentile >= cutoff:
            return ItemVerdict.ALLOW, affinity, percentile, reasons
        if percentile >= cutoff - band:
            reasons.append(
                f"Borderline taste fit: beats {percentile:.0%} of in-city restaurant "
                f"anchors (cutoff {cutoff:.0%} ± {band:.0%}) — allowed with note"
            )
            return ItemVerdict.ALLOW, affinity, percentile, reasons
        reasons.append(
            f"Beats {percentile:.0%} of in-city restaurant anchors "
            f"(needs {cutoff:.0%})"
        )
        return ItemVerdict.REWRITE, affinity, percentile, reasons

    async def fetch_alternatives(
        self,
        *,
        city: str,
        city_center: LatLng,
        signal_entities: list[str],
        exclude_ids: list[str],
        id_labels: dict[str, str] | None = None,
        take: int = 24,
    ) -> list[Alternative]:
        """Persona-ranked restaurant alternatives (signals ON; category+geo gates)."""
        exclude = set(exclude_ids)
        alt_radius = self.settings.alt_radius_km
        raw_rows: list[dict[str, Any]] = []
        # Over-fetch + page: strict restaurant filter drops museums/cultural casas.
        for page in (1, 2, 3, 4):
            if len(raw_rows) >= take * 5:
                break
            payload = await self._alts_insights(
                city=city,
                signal_entities=signal_entities,
                exclude_ids=list(exclude),
                take=50,
                page=page,
                with_radius_zero=True,
            )
            if payload is None and page == 1:
                payload = await self._alts_insights(
                    city=city,
                    signal_entities=signal_entities,
                    exclude_ids=list(exclude),
                    take=50,
                    page=1,
                    with_radius_zero=False,
                )
            if not payload:
                break
            batch = entities_from_insights(payload)
            if not batch:
                break
            raw_rows.extend(batch)

        alts: list[Alternative] = []
        seen: set[str] = set()
        for raw in raw_rows:
            if not is_restaurant_like(raw):
                continue
            loc = extract_latlng(raw)
            if loc is None:
                continue
            dist = haversine_km(city_center, loc)
            if dist > alt_radius:
                continue
            eid = str(raw.get("entity_id") or raw.get("id") or "")
            if not eid or eid in exclude or eid in seen:
                continue
            seen.add(eid)
            alts.append(
                Alternative(
                    entity_id=eid,
                    name=str(raw.get("name") or ""),
                    affinity=affinity_of(raw),
                    distance_km=dist,
                    address=extract_address(raw),
                    locality=extract_locality(raw),
                    explainability_summary=summarize_explainability(
                        explainability_of(raw), id_labels
                    ),
                    replacement_reason="Qloo in-city restaurant alternative",
                )
            )
            if len(alts) >= take:
                break
        if not alts:
            logger.warning(
                "No restaurant-like alternatives after category/geo filter for city=%s",
                city,
            )
        return alts

    async def _alts_insights(
        self,
        *,
        city: str,
        signal_entities: list[str],
        exclude_ids: list[str],
        take: int,
        page: int,
        with_radius_zero: bool,
    ) -> dict[str, Any] | None:
        kwargs: dict[str, Any] = {
            "filter_type": "urn:entity:place",
            "signal_interest_entities": signal_entities or None,
            "filter_exclude_entities": exclude_ids or None,
            "filter_location_query": city,
            "feature_explainability": True,
            "take": take,
            "page": page,
        }
        if with_radius_zero:
            kwargs["filter_location_radius"] = 0
        try:
            return await self.qloo.insights(**kwargs)
        except QlooError as exc:
            if with_radius_zero and exc.status_code == 400:
                return None
            logger.warning("alternatives unavailable: %s", exc)
            return None
