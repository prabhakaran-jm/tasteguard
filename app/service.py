from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.models import (
    CandidateInput,
    EvaluateRequest,
    EvaluationResult,
    EvaluationStatus,
    EvidenceState,
    ItemVerdict,
    PolicyVerdict,
    ScoredCandidate,
)
from app.qloo_client import QlooClient, QlooError
from app.resolver import PlaceResolver
from app.scorer import AnchorScorer

logger = logging.getLogger(__name__)


class TasteGuardService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def resolve_seeds(
        self, qloo: QlooClient, seed_queries: list[dict[str, str]]
    ) -> tuple[list[str], dict[str, str]]:
        ids: list[str] = []
        labels: dict[str, str] = {}
        for seed in seed_queries:
            q = seed.get("query") or ""
            types = seed.get("types") or "urn:entity:place"
            if not q:
                continue
            if types == "urn:tag":
                try:
                    tags = await qloo.tags(q, take=3)
                except QlooError:
                    continue
                for tag in tags:
                    tid = str(tag.get("id") or tag.get("tag_id") or "")
                    if tid:
                        ids.append(tid)
                        labels[tid] = str(tag.get("name") or q)
                continue
            try:
                results = await qloo.search(q, types=types, take=3)
            except QlooError:
                continue
            for entity in results:
                eid = str(entity.get("entity_id") or entity.get("id") or "")
                if eid:
                    ids.append(eid)
                    labels[eid] = str(entity.get("name") or q)
                    break
        seen: set[str] = set()
        uniq: list[str] = []
        for i in ids:
            if i not in seen:
                seen.add(i)
                uniq.append(i)
        return uniq, labels

    async def evaluate(self, request: EvaluateRequest) -> EvaluationResult:
        async with QlooClient(self.settings) as qloo:
            try:
                signal_ids, labels = await self.resolve_seeds(qloo, request.seed_queries)
            except QlooError as exc:
                return EvaluationResult(
                    evaluation_status=EvaluationStatus.UNAVAILABLE,
                    city=request.city,
                    candidates=[],
                    message=f"Qloo unavailable while resolving persona seeds: {exc}",
                )

            if not signal_ids:
                return EvaluationResult(
                    evaluation_status=EvaluationStatus.PARTIAL,
                    city=request.city,
                    candidates=[],
                    message="Could not resolve persona seed entities/tags",
                )

            resolver = PlaceResolver(qloo, self.settings)
            scorer = AnchorScorer(qloo, self.settings)

            hits = [
                await resolver.resolve(
                    cand,
                    city_label=request.city,
                    city_center=request.city_center,
                )
                for cand in request.candidates
            ]

            candidate_ids = [
                h.entity.entity_id
                for h in hits
                if h.entity and h.evidence == EvidenceState.VERIFIED
            ]

            try:
                anchors = await scorer.build_anchors(
                    city=request.city,
                    city_center=request.city_center,
                    signal_entities=signal_ids,
                )
            except QlooError as exc:
                return EvaluationResult(
                    evaluation_status=EvaluationStatus.UNAVAILABLE,
                    city=request.city,
                    candidates=[],
                    message=f"Qloo unavailable while building anchors: {exc}",
                )

            anchor_ids = [a.entity_id for a in anchors]
            status, scored_map, note = await scorer.score_shared_pool(
                signal_entities=signal_ids,
                candidate_ids=candidate_ids,
                anchor_ids=anchor_ids,
                id_labels=labels,
            )

            anchor_affinities = [
                scored_map[a]["affinity"]
                for a in anchor_ids
                if a in scored_map and scored_map[a]["affinity"] is not None
            ]

            scored_candidates: list[ScoredCandidate] = []
            for cand, hit in zip(request.candidates, hits, strict=True):
                eid = hit.entity.entity_id if hit.entity else None
                scored = scored_map.get(eid) if eid else None
                verdict, affinity, percentile, reasons = scorer.item_from_resolve_and_score(
                    hit=hit,
                    scored=scored,
                    anchor_affinities=anchor_affinities,
                    evaluation_status=status,
                )
                scored_candidates.append(
                    ScoredCandidate(
                        input=cand,
                        evidence=hit.evidence,
                        item_verdict=verdict,
                        matched_name=hit.entity.name if hit.entity else None,
                        entity_id=eid,
                        distance_km=hit.distance_km,
                        affinity=affinity,
                        anchor_percentile=percentile,
                        explainability=(scored or {}).get("explainability") or {},
                        explainability_summary=(scored or {}).get("summary"),
                        category_ok=hit.entity.is_restaurant if hit.entity else None,
                        reasons=reasons,
                        kept_unverified=verdict == ItemVerdict.UNKNOWN,
                    )
                )

            policy: PolicyVerdict | None = None
            if status == EvaluationStatus.COMPLETED:
                if all(c.item_verdict == ItemVerdict.ALLOW for c in scored_candidates):
                    policy = PolicyVerdict.PASS
                else:
                    policy = PolicyVerdict.FAIL

            alternatives = []
            if request.fetch_alternatives and policy == PolicyVerdict.FAIL:
                exclude = [c.entity_id for c in scored_candidates if c.entity_id]
                alternatives = await scorer.fetch_alternatives(
                    city=request.city,
                    city_center=request.city_center,
                    signal_entities=signal_ids,
                    exclude_ids=list(dict.fromkeys(exclude)),
                    id_labels=labels,
                )
                unknown_count = sum(
                    1 for c in scored_candidates if c.item_verdict == ItemVerdict.UNKNOWN
                )
                rewrite_count = sum(
                    1 for c in scored_candidates if c.item_verdict == ItemVerdict.REWRITE
                )
                # Honest labels: only mention unverifiable when unknowns exist.
                if unknown_count and not rewrite_count:
                    for alt in alternatives:
                        alt.replacement_reason = (
                            "Replaced because unverifiable, not because off-taste"
                        )
                elif rewrite_count and not unknown_count:
                    for alt in alternatives:
                        alt.replacement_reason = (
                            "Qloo in-city restaurant alternative for policy rewrite"
                        )
                elif unknown_count and rewrite_count:
                    for alt in alternatives:
                        alt.replacement_reason = (
                            "Qloo in-city restaurant alternative "
                            "(covers unverifiable and/or off-taste slots)"
                        )

            messages: list[str] = []
            if note:
                messages.append(note)
            if status == EvaluationStatus.PARTIAL:
                messages.append(
                    "TasteGuard only passes what it can verify; insufficient anchors → no PASS."
                )
            if policy == PolicyVerdict.FAIL:
                unknown_count = sum(
                    1 for c in scored_candidates if c.item_verdict == ItemVerdict.UNKNOWN
                )
                if unknown_count:
                    messages.append(
                        "Unverified items stay on the card as kept/unverified."
                    )
                messages.append(
                    "Repair picks only from the Qloo restaurant alternative pool."
                )

            return EvaluationResult(
                evaluation_status=status,
                policy_verdict=policy,
                city=request.city,
                candidates=scored_candidates,
                alternatives=alternatives,
                anchor_count=len(anchor_affinities),
                message="; ".join(messages) if messages else None,
                notes={
                    "signal_ids": signal_ids,
                    "signal_labels": labels,
                    "anchor_sample": anchor_ids[:10],
                    "scored_ids": list(scored_map.keys()),
                },
            )

    async def repair_until_pass(
        self,
        request: EvaluateRequest,
        *,
        persona_description: str,
        max_rounds: int = 3,
        initial: EvaluationResult | None = None,
    ) -> tuple[EvaluationResult, list[EvaluationResult]]:
        """Closed-set repair up to max_rounds until PASS or exhausted.

        Pass ``initial`` (the evaluation the client already saw) to avoid
        re-running evaluate on that same candidate set. Gemini (or affinity
        fallback) may only pick entity IDs from the FAIL alternatives pool.
        Each subsequent repair round is re-evaluated end-to-end.
        """
        from app.gemini_agent import GeminiConcierge

        history: list[EvaluationResult] = []
        if initial is not None:
            current = initial
        else:
            current = await self.evaluate(request)
        history.append(current)

        if current.policy_verdict == PolicyVerdict.PASS:
            return current, history

        agent = GeminiConcierge(self.settings)
        working = request

        for round_idx in range(1, max_rounds + 1):
            if not current.alternatives:
                current.message = (
                    (current.message or "")
                    + f"; repair round {round_idx} skipped — empty alternative pool"
                ).lstrip("; ")
                break

            reasons = [r for c in current.candidates for r in c.reasons][:12]
            # Keep repaired list length aligned with the unguarded / current list.
            target_n = max(len(working.candidates), 1)
            chosen_ids = await agent.repair_from_pool(
                city=working.city,
                persona_description=persona_description,
                fail_reasons=reasons,
                alternatives=current.alternatives,
                n=min(target_n, len(current.alternatives)),
            )
            by_id = {a.entity_id: a for a in current.alternatives}
            repaired: list[CandidateInput] = []
            for eid in chosen_ids:
                alt = by_id.get(eid)
                if not alt:
                    continue
                repaired.append(
                    CandidateInput(
                        name=alt.name,
                        neighbourhood=alt.locality,
                        address=alt.address,
                        notes=f"Closed-set repair round {round_idx}",
                    )
                )
            if not repaired:
                current.message = (
                    (current.message or "")
                    + f"; repair round {round_idx} produced no valid pool picks"
                ).lstrip("; ")
                break

            working = EvaluateRequest(
                city=working.city,
                city_center=working.city_center,
                seed_queries=working.seed_queries,
                candidates=repaired,
                fetch_alternatives=True,
            )
            current = await self.evaluate(working)
            current.notes = {
                **current.notes,
                "repair_round": round_idx,
                "chosen_entity_ids": chosen_ids,
            }
            history.append(current)
            if current.policy_verdict == PolicyVerdict.PASS:
                break

        return current, history
