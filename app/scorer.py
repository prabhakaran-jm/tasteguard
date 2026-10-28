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
        signal_entities: list[str],
    ) -> list[PlaceEntity]:
        anchors: list[PlaceEntity] = []
        seen: set[str] = set()
        for pop_min, pop_max, page in (
            (0.55, 0.95, 1),
            (0.40, 0.85, 1),
            (0.40, 0.85, 2),
        ):
            if len(anchors) >= self.settings.anchor_target:
                break
            try:
                payload = await self.qloo.insights(
                    filter_type="urn:entity:place",
                    signal_interest_entities=signal_entities or None,
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
                if not is_restaurant_like(raw):
                    continue
                eid = str(raw.get("entity_id") or raw.get("id") or "")
                if not eid or eid in seen:
                    continue
                loc = extract_latlng(raw)
                if loc is None:
                    continue
                dist = haversine_km(city_center, loc)
                if dist > self.settings.near_radius_km:
                    continue
                seen.add(eid)
                anchors.append(
                    PlaceEntity(
                        entity_id=eid,
                        name=str(raw.get("name") or ""),
                        location=loc,
                        address=extract_address(raw),
                        locality=extract_locality(raw),
                        is_restaurant=True,
                        raw=raw,
                    )
                )
                if len(anchors) >= self.settings.anchor_target:
                    break
        return anchors

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
        if affinity is None or evaluation_status != EvaluationStatus.COMPLETED:
            reasons.append(
                "Affinity unscored or evaluation not completed — informational only"
            )
            return ItemVerdict.UNKNOWN, affinity, None, reasons

        percentile = self.relative_percentile(affinity, anchor_affinities)
        if percentile >= self.settings.allow_anchor_percentile:
            return ItemVerdict.ALLOW, affinity, percentile, reasons
        reasons.append(
            f"Below allow cutoff among anchors "
            f"(percentile {percentile:.2f} < {self.settings.allow_anchor_percentile:.2f})"
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
        take: int = 12,
    ) -> list[Alternative]:
        try:
            payload = await self.qloo.insights(
                filter_type="urn:entity:place",
                signal_interest_entities=signal_entities or None,
                filter_exclude_entities=exclude_ids or None,
                filter_location_query=city,
                filter_location_radius=0,
                feature_explainability=True,
                take=take,
            )
        except QlooError as exc:
            if exc.status_code == 400:
                try:
                    payload = await self.qloo.insights(
                        filter_type="urn:entity:place",
                        signal_interest_entities=signal_entities or None,
                        filter_exclude_entities=exclude_ids or None,
                        filter_location_query=city,
                        feature_explainability=True,
                        take=take,
                    )
                except QlooError as exc2:
                    logger.warning("alternatives unavailable: %s", exc2)
                    return []
            else:
                logger.warning("alternatives unavailable: %s", exc)
                return []

        alts: list[Alternative] = []
        for raw in entities_from_insights(payload):
            if not is_restaurant_like(raw):
                continue
            loc = extract_latlng(raw)
            if loc is None:
                continue
            dist = haversine_km(city_center, loc)
            if dist > self.settings.near_radius_km:
                continue
            eid = str(raw.get("entity_id") or raw.get("id") or "")
            if not eid or eid in exclude_ids:
                continue
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
        return alts
