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


def _join_messages(parts: list[str]) -> str | None:
    cleaned: list[str] = []
    for part in parts:
        text = str(part or "").strip().strip(";").strip()
        if text.endswith("."):
            text = text[:-1].rstrip()
        if text:
            cleaned.append(text)
    if not cleaned:
        return None
    return ". ".join(cleaned) + "."


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
            allow_count = sum(
                1 for c in scored_candidates if c.item_verdict == ItemVerdict.ALLOW
            )
            # PASS only with exactly N ALLOW restaurants — no unknowns, no rewrites.
            if status == EvaluationStatus.COMPLETED:
                if not length_ok:
                    policy = PolicyVerdict.FAIL
                    length_msg = (
                        f"List length {len(scored_candidates)} ≠ expected "
                        f"{expected_n} — cannot PASS"
                    )
                    note = f"{note}. {length_msg}" if note else length_msg
                elif allow_count == int(expected_n) and all(
                    c.item_verdict == ItemVerdict.ALLOW for c in scored_candidates
                ):
                    policy = PolicyVerdict.PASS
                else:
                    policy = PolicyVerdict.FAIL

            alternatives = []
            if request.fetch_alternatives and policy == PolicyVerdict.FAIL:
                exclude = [c.entity_id for c in scored_candidates if c.entity_id]
                exclude = list(
                    dict.fromkeys(exclude + list(request.exclude_entity_ids or []))
                )
                alternatives = await scorer.fetch_alternatives(
                    city=request.city,
                    city_center=request.city_center,
                    signal_entities=signal_ids,
                    exclude_ids=exclude,
                    id_labels=labels,
                    take=max(24, rewrite_count + unknown_count + 8),
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
                messages.append(note.rstrip(".; "))
            if status == EvaluationStatus.PARTIAL:
                messages.append(
                    "TasteGuard only passes what it can verify; insufficient anchors → no PASS"
                )
            # Concrete per-item reasons for the FAIL/PASS banner.
            problem_lines = [
                f"{c.input.name}: {c.reasons[-1]}"
                for c in scored_candidates
                if c.item_verdict != ItemVerdict.ALLOW and c.reasons
            ]
            if policy == PolicyVerdict.FAIL:
                if problem_lines:
                    messages.extend(problem_lines[:6])
                else:
                    messages.append("Policy FAIL — see item evidence")
                if allow_count < int(expected_n):
                    messages.append(
                        f"{allow_count}/{expected_n} ALLOW — need {expected_n} "
                        "validated restaurants to PASS"
                    )
            elif policy == PolicyVerdict.PASS:
                messages.append(
                    f"PASS — {allow_count} validated restaurants vs {request.city} anchors"
                )

            return EvaluationResult(
                evaluation_status=status,
                policy_verdict=policy,
                city=request.city,
                candidates=scored_candidates,
                alternatives=alternatives,
                anchor_count=len(anchor_affinities),
                message=_join_messages(messages),
                notes={
                    "signal_ids": signal_ids,
                    "signal_labels": labels,
                    "anchor_sample": anchor_ids[:10],
                    "anchor_city": request.city,
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

        Keep every ALLOW (pinned by entity_id). Replace only rewrite/unknown
        slots from a pre-validated alternative pool. Never re-search pool picks
        by name. If Gemini returns invalid IDs, fall back to top affinity.
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
        target_n = max(
            int(request.expected_count or 0),
            len(baseline.candidates),
            1,
        )
        tried_ids: set[str] = set(request.exclude_entity_ids or [])

        for round_idx in range(1, max_rounds + 1):
            for c in current.candidates:
                if c.entity_id:
                    tried_ids.add(c.entity_id)

            # Surgical: keep ALLOW rows pinned; replace rewrite/unknown only.
            keep: list[CandidateInput] = []
            rejected: list[ScoredCandidate] = []
            for c in current.candidates:
                if c.item_verdict == ItemVerdict.ALLOW:
                    keep.append(
                        CandidateInput(
                            name=(c.matched_name or c.input.name)[:120],
                            neighbourhood=c.input.neighbourhood,
                            address=c.input.address,
                            notes="Kept after TasteGuard allow",
                            entity_id=c.entity_id,
                            pinned_distance_km=c.distance_km,
                            pinned_locality=c.input.neighbourhood,
                        )
                    )
                else:
                    rejected.append(c)

            replace_slots = target_n - len(keep)
            if replace_slots <= 0:
                # Already have enough allows — re-check length only.
                if len(keep) >= target_n:
                    current.policy_verdict = PolicyVerdict.PASS
                    current.message = (
                        f"PASS — {len(keep)} validated restaurants "
                        f"(repair round {round_idx} had nothing to replace)"
                    )
                    history.append(current)
                    break
                replace_slots = max(len(rejected), 1)

            pool = [
                a for a in current.alternatives if a.entity_id not in tried_ids
            ]
            if len(pool) < replace_slots:
                # Fresh pool excluding everything already tried / kept.
                async with QlooClient(self.settings) as qloo:
                    signal_ids, labels = await self.resolve_seeds(
                        qloo, working.seed_queries
                    )
                    scorer = AnchorScorer(qloo, self.settings)
                    extra = await scorer.fetch_alternatives(
                        city=working.city,
                        city_center=working.city_center,
                        signal_entities=signal_ids,
                        exclude_ids=list(tried_ids),
                        id_labels=labels,
                        take=max(24, replace_slots + 12),
                    )
                seen_pool = {a.entity_id for a in pool}
                for alt in extra:
                    if alt.entity_id not in seen_pool and alt.entity_id not in tried_ids:
                        pool.append(alt)
                        seen_pool.add(alt.entity_id)

            if not pool:
                current.message = _join_messages(
                    [
                        current.message or "",
                        f"Repair round {round_idx} failed — empty alternative pool "
                        f"after excluding {len(tried_ids)} tried IDs "
                        f"({len(keep)}/{target_n} ALLOW kept)",
                    ]
                )
                break

            by_id = {a.entity_id: a for a in pool}
            keep_names = {k.name.casefold() for k in keep}
            ranked = sorted(
                pool,
                key=lambda a: (a.affinity is not None, a.affinity or 0.0),
                reverse=True,
            )
            reasons = [r for c in rejected for r in c.reasons][:12]
            n_pick = min(replace_slots, len(pool))
            chosen_ids = await agent.repair_from_pool(
                city=working.city,
                persona_description=persona_description,
                fail_reasons=reasons,
                alternatives=pool,
                n=n_pick,
            )
            # Affinity fallback if Gemini returned nothing usable.
            valid_chosen = [eid for eid in chosen_ids if eid in by_id]
            if len(valid_chosen) < n_pick:
                for alt in ranked:
                    if alt.entity_id in valid_chosen:
                        continue
                    valid_chosen.append(alt.entity_id)
                    if len(valid_chosen) >= n_pick:
                        break

            replacements: list[CandidateInput] = []
            used: set[str] = set()
            for eid in valid_chosen:
                alt = by_id.get(eid)
                if not alt or eid in used:
                    continue
                if alt.name.casefold() in keep_names:
                    continue
                used.add(eid)
                tried_ids.add(eid)
                replacements.append(
                    CandidateInput(
                        name=alt.name[:120],
                        neighbourhood=alt.locality,
                        address=alt.address,
                        notes=(
                            f"Closed-set repair round {round_idx}: "
                            f"{alt.replacement_reason or 'pool pick'}"
                        )[:200],
                        entity_id=alt.entity_id,
                        pinned_distance_km=alt.distance_km,
                        pinned_locality=alt.locality,
                    )
                )
                if len(replacements) >= replace_slots:
                    break

            repaired = (keep + replacements)[:target_n]
            # Pad from ranked pool if still short (unique by entity_id / name).
            seen_eids = {c.entity_id for c in repaired if c.entity_id}
            seen_names = {c.name.casefold() for c in repaired}
            for alt in ranked:
                if len(repaired) >= target_n:
                    break
                if alt.entity_id in seen_eids or alt.name.casefold() in seen_names:
                    continue
                seen_eids.add(alt.entity_id)
                seen_names.add(alt.name.casefold())
                tried_ids.add(alt.entity_id)
                repaired.append(
                    CandidateInput(
                        name=alt.name[:120],
                        neighbourhood=alt.locality,
                        address=alt.address,
                        notes=f"Closed-set repair pad round {round_idx}"[:200],
                        entity_id=alt.entity_id,
                        pinned_distance_km=alt.distance_km,
                        pinned_locality=alt.locality,
                    )
                )

            swapped: list[str] = []
            for i, old in enumerate(rejected):
                if i < len(replacements):
                    swapped.append(f"{old.input.name} → {replacements[i].name}")

            if len(repaired) < target_n:
                current.message = _join_messages(
                    [
                        current.message or "",
                        f"Repair round {round_idx} pool too small "
                        f"({len(repaired)} < {target_n}) — partial repair failure",
                    ]
                )
                if not repaired:
                    break
                # Still evaluate what we have (will FAIL closed on length).

            working = EvaluateRequest(
                city=working.city,
                city_center=working.city_center,
                seed_queries=working.seed_queries,
                candidates=repaired,
                fetch_alternatives=True,
                expected_count=target_n,
                exclude_entity_ids=list(tried_ids),
            )
            current = await self.evaluate(working)
            current.notes = {
                **current.notes,
                "repair_round": round_idx,
                "chosen_entity_ids": list(used),
                "expected_count": target_n,
                "kept_allows": len(keep),
                "replaced": swapped,
                "tried_ids_count": len(tried_ids),
                "pool_size": len(pool),
            }
            if swapped:
                current.message = _join_messages(
                    [
                        f"Repaired in {round_idx} round"
                        f"{'s' if round_idx != 1 else ''}: "
                        + "; ".join(swapped),
                        current.message or "",
                    ]
                )
            history.append(current)
            if current.policy_verdict == PolicyVerdict.PASS:
                break

        return current, history
