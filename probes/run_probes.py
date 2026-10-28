#!/usr/bin/env python3
"""Day-1 Qloo launch-gate probes. Requires QLOO_API_KEY in the environment or .env."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.qloo_client import (
    QlooClient,
    QlooError,
    affinity_of,
    entities_from_insights,
    explainability_of,
    extract_address,
    extract_latlng,
)

# Lisbon city center — used for filter.location=lat,lon on Search
LISBON = "38.7223,-9.1393"
NYC = "40.7580,-73.9855"


def pp(title: str, payload: object) -> None:
    print(f"\n=== {title} ===")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, default=str)[:4000])
    else:
        print(payload)


async def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.qloo_api_key:
        print("FAIL: QLOO_API_KEY not set. Copy .env.example to .env and add your key.")
        return 2

    gates: dict[str, dict] = {}
    report: dict[str, object] = {
        "base_url": settings.qloo_base_url,
        "gates": gates,
    }

    async with QlooClient(settings) as qloo:
        # 1. Auth + search (global, no location filter)
        try:
            results = await qloo.search("Ramiro", types="urn:entity:place", take=5)
            gates["auth_search"] = {
                "ok": True,
                "count": len(results),
                "sample": [
                    {
                        "id": r.get("entity_id") or r.get("id"),
                        "name": r.get("name"),
                        "latlng": extract_latlng(r),
                        "address": extract_address(r),
                        "keys": sorted(list(r.keys()))[:30],
                        "property_keys": sorted(
                            list((r.get("properties") or {}).keys())
                        )[:40],
                    }
                    for r in results[:3]
                ],
            }
            pp("auth_search", gates["auth_search"])
        except QlooError as exc:
            gates["auth_search"] = {"ok": False, "error": str(exc)}
            pp("auth_search FAILED", gates["auth_search"])
            _write(report)
            return 1

        geo_ok = any(
            (s.get("latlng") or s.get("address"))
            for s in gates["auth_search"]["sample"]  # type: ignore[index]
        )
        gates["geo_metadata"] = {
            "ok": geo_ok,
            "note": "coords/address present on search hits (required for distance grading)",
        }
        pp("geo_metadata", gates["geo_metadata"])

        # 2. Location-constrained search with lat,lon (not city name)
        try:
            local = await qloo.search(
                "Cervejaria Ramiro",
                types="urn:entity:place",
                filter_location_latlon=LISBON,
                filter_radius_miles=10,
                take=5,
            )
            gates["search_latlon"] = {
                "ok": True,
                "count": len(local),
                "names": [r.get("name") for r in local[:5]],
                "ids": [r.get("entity_id") or r.get("id") for r in local[:5]],
            }
        except QlooError as exc:
            gates["search_latlon"] = {"ok": False, "error": str(exc)}
        pp("search_latlon", gates["search_latlon"])

        # 3. Seed entity for Insights signals
        seed_hits = await qloo.search("Radiohead", types="urn:entity:artist", take=3)
        if not seed_hits:
            seed_hits = await qloo.search(
                "Eleven Madison Park", types="urn:entity:place", take=3
            )
        seed_id = str(
            (seed_hits[0].get("entity_id") or seed_hits[0].get("id"))
            if seed_hits
            else ""
        )
        gates["seed"] = {
            "ok": bool(seed_id),
            "id": seed_id,
            "name": seed_hits[0].get("name") if seed_hits else None,
        }
        pp("seed", gates["seed"])
        if not seed_id:
            _write(report)
            return 1

        # Candidate place for affinity probes
        place_hits = local if gates.get("search_latlon", {}).get("ok") and local else (
            await qloo.search("Le Bernardin", types="urn:entity:place", take=5)
        )
        if not place_hits:
            gates["candidate_place"] = {"ok": False, "error": "no place hits"}
            _write(report)
            return 1
        place_a = place_hits[0]
        place_a_id = str(place_a.get("entity_id") or place_a.get("id"))
        gates["candidate_place"] = {
            "ok": bool(place_a_id),
            "id": place_a_id,
            "name": place_a.get("name"),
            "latlng": extract_latlng(place_a),
            "address": extract_address(place_a),
        }
        pp("candidate_place", gates["candidate_place"])

        # 4. Wrong-city identity (global search for a non-Lisbon landmark)
        wrong = await qloo.search("The French Laundry", types="urn:entity:place", take=5)
        gates["wrong_city_identity"] = {
            "ok": bool(wrong),
            "hits": [
                {
                    "id": w.get("entity_id") or w.get("id"),
                    "name": w.get("name"),
                    "latlng": extract_latlng(w),
                    "address": extract_address(w),
                }
                for w in wrong[:3]
            ],
        }
        pp("wrong_city_identity", gates["wrong_city_identity"])

        # 5. Insights affinity + explainability
        try:
            single = await qloo.insights(
                filter_type="urn:entity:place",
                signal_interest_entities=[seed_id],
                filter_results_entities=[place_a_id],
                feature_explainability=True,
                take=5,
            )
            ents = [
                e
                for e in entities_from_insights(single)
                if str(e.get("entity_id") or e.get("id")) == place_a_id
            ]
            aff = affinity_of(ents[0]) if ents else None
            expl = explainability_of(ents[0]) if ents else {}
            gates["insights_affinity"] = {
                "ok": aff is not None,
                "affinity": aff,
                "affinity_type": type(aff).__name__ if aff is not None else None,
                "explainability": expl,
                "entity_keys": sorted(list(ents[0].keys())) if ents else [],
                "query_keys": sorted(list((ents[0].get("query") or {}).keys()))
                if ents
                else [],
            }
        except QlooError as exc:
            gates["insights_affinity"] = {"ok": False, "error": str(exc)}
        pp("insights_affinity", gates["insights_affinity"])

        # 6. SET DEPENDENCE (most important): A alone vs A + peers
        others = await qloo.search(
            "restaurant",
            types="urn:entity:place",
            filter_location_latlon=LISBON,
            filter_radius_miles=8,
            take=8,
        )
        if len(others) < 4:
            others = await qloo.search(
                "restaurant",
                types="urn:entity:place",
                filter_location_latlon=NYC,
                filter_radius_miles=8,
                take=8,
            )
        other_ids = [
            str(o.get("entity_id") or o.get("id"))
            for o in others
            if str(o.get("entity_id") or o.get("id")) != place_a_id
        ][:4]

        async def score_set(ids: list[str]) -> float | None:
            payload = await qloo.insights(
                filter_type="urn:entity:place",
                signal_interest_entities=[seed_id],
                filter_results_entities=ids,
                feature_explainability=False,
                take=min(50, len(ids)),
            )
            for e in entities_from_insights(payload):
                if str(e.get("entity_id") or e.get("id")) == place_a_id:
                    return affinity_of(e)
            return None

        try:
            alone = await score_set([place_a_id])
            with_peers = await score_set([place_a_id, *other_ids])
            changed = (
                alone is not None and with_peers is not None and alone != with_peers
            )
            gates["set_dependence"] = {
                "ok": True,
                "affinity_alone": alone,
                "affinity_with_peers": with_peers,
                "peer_ids": other_ids,
                "changed": changed,
                "interpretation": (
                    "SET-RELATIVE: affinity changed with peer set — use anchor-relative cutoffs"
                    if changed
                    else "STABLE or incomplete — still prefer shared-pool scoring"
                ),
            }
        except QlooError as exc:
            gates["set_dependence"] = {"ok": False, "error": str(exc)}
        pp("set_dependence", gates["set_dependence"])

        # 7. filter.results.entities capacity + backfill extras
        many_ids = [place_a_id, *other_ids]
        extra = await qloo.search(
            "cafe",
            types="urn:entity:place",
            filter_location_latlon=NYC,
            filter_radius_miles=5,
            take=40,
        )
        for o in extra:
            eid = str(o.get("entity_id") or o.get("id"))
            if eid and eid not in many_ids:
                many_ids.append(eid)
            if len(many_ids) >= 40:
                break
        try:
            big = await qloo.insights(
                filter_type="urn:entity:place",
                signal_interest_entities=[seed_id],
                filter_results_entities=many_ids,
                feature_explainability=False,
                take=50,
            )
            returned = {
                str(e.get("entity_id") or e.get("id"))
                for e in entities_from_insights(big)
            }
            gates["filter_results_capacity"] = {
                "ok": True,
                "sent": len(many_ids),
                "returned_requested": len(returned & set(many_ids)),
                "returned_total": len(returned),
                "backfill_extras": len(returned - set(many_ids)),
            }
        except QlooError as exc:
            gates["filter_results_capacity"] = {
                "ok": False,
                "error": str(exc),
                "sent": len(many_ids),
            }
        pp("filter_results_capacity", gates["filter_results_capacity"])

        # 8. Same place with vs without filter.location.query on Insights
        try:
            no_loc = await qloo.insights(
                filter_type="urn:entity:place",
                signal_interest_entities=[seed_id],
                filter_results_entities=[place_a_id],
                feature_explainability=False,
                take=5,
            )
            with_loc = await qloo.insights(
                filter_type="urn:entity:place",
                signal_interest_entities=[seed_id],
                filter_results_entities=[place_a_id],
                filter_location_query="Lisbon",
                feature_explainability=False,
                take=5,
            )

            def aff_for(payload: dict) -> float | None:
                for e in entities_from_insights(payload):
                    if str(e.get("entity_id") or e.get("id")) == place_a_id:
                        return affinity_of(e)
                return None

            a1, a2 = aff_for(no_loc), aff_for(with_loc)
            gates["location_filter_comparability"] = {
                "ok": True,
                "affinity_no_location_filter": a1,
                "affinity_with_location_filter": a2,
                "same": a1 == a2,
                "note": "Plan locks affinity calls WITHOUT filter.location",
            }
        except QlooError as exc:
            gates["location_filter_comparability"] = {"ok": False, "error": str(exc)}
        pp("location_filter_comparability", gates["location_filter_comparability"])

        # 9. Alternatives with filter.location.radius=0 (may 400 — record that)
        try:
            alts = await qloo.insights(
                filter_type="urn:entity:place",
                signal_interest_entities=[seed_id],
                filter_location_query="Lisbon",
                filter_location_radius=0,
                feature_explainability=True,
                take=10,
            )
            gates["alternatives_radius0"] = {
                "ok": True,
                "count": len(entities_from_insights(alts)),
                "names": [e.get("name") for e in entities_from_insights(alts)[:5]],
            }
        except QlooError as exc:
            gates["alternatives_radius0"] = {
                "ok": False,
                "error": str(exc),
                "status_code": exc.status_code,
                "note": "Unsupported radius=0 is OK — service will fall back without it",
            }
        pp("alternatives_radius0", gates["alternatives_radius0"])

    _write(report)
    failed = [
        k for k, v in gates.items() if isinstance(v, dict) and v.get("ok") is False
    ]
    # alternatives_radius0 failure is informational, not a hard fail
    hard = [k for k in failed if k != "alternatives_radius0"]
    print("\n==== SUMMARY ====")
    print("hard_failed_gates:", hard or "none")
    print("informational_failed:", [k for k in failed if k not in hard] or "none")
    print("report: probes/probe_report.json (gitignored)")
    return 1 if hard else 0


def _write(report: dict) -> None:
    out = ROOT / "probes" / "probe_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
