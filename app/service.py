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
                confident = hit.evidence in (
                    EvidenceState.VERIFIED,
                    EvidenceState.MISMATCH,
                )
                eid = hit.entity.entity_id if hit.entity and confident else None
                scored = scored_map.get(eid) if eid else None
                verdict, affinity, percentile, reasons = scorer.item_from_resolve_and_score(
                    hit=hit,
                    scored=scored,
                    anchor_affinities=anchor_affinities,
                    evaluation_status=status,
                )
                if hit.evidence in (
                    EvidenceState.UNKNOWN,
                    EvidenceState.NO_CONFIDENT_MATCH,
                ):
                    reasons = [
                        r
                        for r in reasons
                        if "Ambiguous match" not in r and "similarity" not in r
                    ]
                    if not any("No confident Qloo match" in r for r in reasons):
                        reasons.append("No confident Qloo match")

                scored_candidates.append(
                    ScoredCandidate(
                        input=cand,
                        evidence=hit.evidence,
                        item_verdict=verdict,
                        matched_name=(
                            hit.entity.name if hit.entity and confident else None
                        ),
                        entity_id=eid,
                        distance_km=hit.distance_km if confident else None,
                        affinity=affinity,
                        anchor_percentile=percentile,
                        explainability=(scored or {}).get("explainability") or {},
                        explainability_summary=(scored or {}).get("summary"),
                        category_ok=(
                            hit.entity.is_restaurant if hit.entity and confident else None
                        ),
                        reasons=reasons,
                        kept_unverified=verdict == ItemVerdict.UNKNOWN,
                    )
                )

            policy: PolicyVerdict | None = None
            expected_n = request.expected_count or len(request.candidates)
            length_ok = len(scored_candidates) == int(expected_n)
            unknown_count = sum(
                1 for c in scored_candidates if c.item_verdict == ItemVerdict.UNKNOWN
            )
            rewrite_count = sum(
                1 for c in scored_candidates if c.item_verdict == ItemVerdict.REWRITE
            )
            # Product rule: ≤1 unknown may stay kept/unverified; any rewrite FAILS.
            # More than one unknown also FAILS.
            if status == EvaluationStatus.COMPLETED:
                if not length_ok:
                    policy = PolicyVerdict.FAIL
                    note = (
                        f"{note}; List length {len(scored_candidates)} ≠ expected "
                        f"{expected_n} — cannot PASS"
                        if note
                        else (
                            f"List length {len(scored_candidates)} ≠ expected "
                            f"{expected_n} — cannot PASS"
                        )
                    )
                elif rewrite_count > 0 or unknown_count > 1:
                    policy = PolicyVerdict.FAIL
                elif unknown_count <= 1 and all(
                    c.item_verdict in (ItemVerdict.ALLOW, ItemVerdict.UNKNOWN)
                    for c in scored_candidates
                ):
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
            # Concrete per-item reasons for the FAIL/PASS banner (not generic boilerplate).
            problem_lines = [
                f"{c.input.name}: {c.reasons[-1]}"
                for c in scored_candidates
                if c.item_verdict != ItemVerdict.ALLOW and c.reasons
            ]
            if policy == PolicyVerdict.FAIL:
                if problem_lines:
                    messages.extend(problem_lines[:6])
                else:
                    messages.append("Policy FAIL — see item evidence.")
                if unknown_count == 1 and rewrite_count == 0:
                    messages.append(
                        "One unverified item may stay kept/unverified; "
                        "more than one unknown fails the card."
                    )
            elif policy == PolicyVerdict.PASS and unknown_count == 1:
                kept = next(
                    c for c in scored_candidates if c.item_verdict == ItemVerdict.UNKNOWN
                )
                messages.append(
                    f"PASS with one kept/unverified item: {kept.input.name}"
                    + (f" — {kept.reasons[-1]}" if kept.reasons else "")
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
        baseline = initial if initial is not None else current
        target_n = max(len(baseline.candidates), 1)

        for round_idx in range(1, max_rounds + 1):
            if not current.alternatives:
                current.message = (
                    (current.message or "")
                    + f"; repair round {round_idx} skipped — empty alternative pool"
                ).lstrip("; ")
                break

            # Surgical repair: keep ALLOW rows; replace only rewrite/unknown slots.
            keep: list[CandidateInput] = []
            replace_slots = 0
            for c in current.candidates:
                if c.item_verdict == ItemVerdict.ALLOW:
                    keep.append(
                        CandidateInput(
                            name=(c.matched_name or c.input.name)[:120],
                            neighbourhood=c.input.neighbourhood,
                            address=c.input.address,
                            notes="Kept after TasteGuard allow",
                        )
                    )
                else:
                    replace_slots += 1

            by_id = {a.entity_id: a for a in current.alternatives}
            keep_names = {k.name.casefold() for k in keep}
            ranked = sorted(
                current.alternatives,
                key=lambda a: (a.affinity is not None, a.affinity or 0.0),
                reverse=True,
            )
            reasons = [r for c in current.candidates for r in c.reasons][:12]
            chosen_ids = await agent.repair_from_pool(
                city=working.city,
                persona_description=persona_description,
                fail_reasons=reasons,
                alternatives=current.alternatives,
                n=min(max(replace_slots, 1), len(current.alternatives)),
            )
            replacements: list[CandidateInput] = []
            used: set[str] = set()
            for eid in chosen_ids + [a.entity_id for a in ranked]:
                alt = by_id.get(eid)
                if not alt or eid in used:
                    continue
                if alt.name.casefold() in keep_names:
                    continue
                used.add(eid)
                replacements.append(
                    CandidateInput(
                        name=alt.name[:120],
                        neighbourhood=alt.locality,
                        address=alt.address,
                        notes=f"Closed-set repair round {round_idx}",
                    )
                )
                if len(replacements) >= replace_slots:
                    break

            repaired = keep + replacements
            # Unique by name; pad from pool if short.
            uniq: list[CandidateInput] = []
            seen_names: set[str] = set()
            for c in repaired:
                key = c.name.casefold()
                if key in seen_names:
                    continue
                seen_names.add(key)
                uniq.append(c)
            for alt in ranked:
                if len(uniq) >= target_n:
                    break
                if alt.name.casefold() in seen_names:
                    continue
                seen_names.add(alt.name.casefold())
                uniq.append(
                    CandidateInput(
                        name=alt.name[:120],
                        neighbourhood=alt.locality,
                        address=alt.address,
                        notes=f"Closed-set repair pad round {round_idx}",
                    )
                )
            repaired = uniq[:target_n]

            swapped = [
                f"{c.input.name} → {replacements[i].name}"
                for i, c in enumerate(
                    [x for x in current.candidates if x.item_verdict != ItemVerdict.ALLOW]
                )
                if i < len(replacements)
            ]

            if len(repaired) < target_n:
                current.message = (
                    (current.message or "")
                    + f"; repair round {round_idx} pool too small "
                    f"({len(repaired)} < {target_n}) — cannot PASS"
                ).lstrip("; ")
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
                expected_count=target_n,
            )
            current = await self.evaluate(working)
            current.notes = {
                **current.notes,
                "repair_round": round_idx,
                "chosen_entity_ids": list(used),
                "expected_count": target_n,
                "kept_allows": len(keep),
                "replaced": swapped,
            }
            if swapped:
                current.message = (
                    f"Repaired in {round_idx} round"
                    f"{'s' if round_idx != 1 else ''}: "
                    + "; ".join(swapped)
                )
            history.append(current)
            if current.policy_verdict == PolicyVerdict.PASS:
                break

        return current, history
