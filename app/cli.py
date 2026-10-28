from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich import print

from app.geo import LatLng
from app.models import CandidateInput, EvaluateRequest
from app.service import TasteGuardService

app = typer.Typer(
    add_completion=False,
    help="TasteGuard CLI",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """TasteGuard — cultural quality gate for place agents."""


@app.command("evaluate")
def evaluate(
    city: str = typer.Option("Lisbon", help="City label for geo checks and Insights location"),
    lat: float = typer.Option(38.7223, help="City center latitude"),
    lon: float = typer.Option(-9.1393, help="City center longitude"),
    seed: Optional[list[str]] = typer.Option(
        None,
        "--seed",
        "-s",
        help="Persona seed as type:query (e.g. artist:Radiohead). Repeatable.",
    ),
    candidate: Optional[list[str]] = typer.Option(
        None,
        "--candidate",
        "-c",
        help="Candidate restaurant name. Repeatable.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print full JSON result"),
    no_alternatives: bool = typer.Option(
        False, "--no-alternatives", help="Skip repair alternative fetch on FAIL"
    ),
) -> None:
    """Resolve + score candidates against Qloo with anchor-relative affinity."""
    seeds_raw = seed or ["artist:Radiohead"]
    candidates_raw = candidate or [
        "Cervejaria Ramiro",
        "The French Laundry",
    ]

    seed_queries: list[dict[str, str]] = []
    for item in seeds_raw:
        if ":" in item:
            kind, _, query = item.partition(":")
            type_map = {
                "artist": "urn:entity:artist",
                "place": "urn:entity:place",
                "movie": "urn:entity:movie",
                "brand": "urn:entity:brand",
                "tag": "urn:tag",
                "person": "urn:entity:person",
                "tv": "urn:entity:tv_show",
            }
            types = type_map.get(kind.lower(), kind)
            seed_queries.append({"query": query, "types": types})
        else:
            seed_queries.append({"query": item, "types": "urn:entity:artist"})

    request = EvaluateRequest(
        city=city,
        city_center=LatLng(lat=lat, lon=lon),
        seed_queries=seed_queries,
        candidates=[CandidateInput(name=n) for n in candidates_raw],
        fetch_alternatives=not no_alternatives,
    )
    result = asyncio.run(TasteGuardService().evaluate(request))

    if json_out:
        print(json.dumps(result.model_dump(), indent=2, default=str))
        return

    print(
        f"[bold]status[/bold]={result.evaluation_status.value} "
        f"[bold]verdict[/bold]={result.policy_verdict} "
        f"[bold]anchors[/bold]={result.anchor_count}"
    )
    if result.message:
        print(f"[dim]{result.message}[/dim]")
    for c in result.candidates:
        print(
            f"- {c.input.name}: {c.evidence.value}/{c.item_verdict.value} "
            f"match={c.matched_name!r} km={c.distance_km} "
            f"aff={c.affinity} pct={c.anchor_percentile}"
        )
    if result.alternatives:
        print("[bold]alternatives[/bold]:")
        for a in result.alternatives[:8]:
            print(f"  * {a.name} ({a.entity_id[:8]}…) aff={a.affinity}")


if __name__ == "__main__":
    app()
