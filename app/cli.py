from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich import print

from app.geo import LatLng
from app.models import CandidateInput, EvaluateRequest, PolicyVerdict
from app.service import TasteGuardService

app = typer.Typer(
    add_completion=False,
    help="TasteGuard CLI",
    no_args_is_help=True,
)

TYPE_MAP = {
    "artist": "urn:entity:artist",
    "place": "urn:entity:place",
    "movie": "urn:entity:movie",
    "brand": "urn:entity:brand",
    "tag": "urn:tag",
    "person": "urn:entity:person",
    "tv": "urn:entity:tv_show",
}


@app.callback()
def _root() -> None:
    """TasteGuard — cultural quality gate for place agents."""


def _parse_seeds(seed: list[str] | None) -> list[dict[str, str]]:
    seeds_raw = seed or ["artist:Radiohead"]
    seed_queries: list[dict[str, str]] = []
    for item in seeds_raw:
        if ":" in item:
            kind, _, query = item.partition(":")
            types = TYPE_MAP.get(kind.lower(), kind)
            seed_queries.append({"query": query, "types": types})
        else:
            seed_queries.append({"query": item, "types": "urn:entity:artist"})
    return seed_queries


def _print_result(result, *, label: str = "") -> None:
    prefix = f"{label} " if label else ""
    print(
        f"{prefix}[bold]status[/bold]={result.evaluation_status.value} "
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
            f"{' [kept, unverified]' if c.kept_unverified else ''}"
        )
    if result.alternatives:
        print("[bold]alternatives[/bold]:")
        for a in result.alternatives[:8]:
            reason = a.replacement_reason or ""
            print(f"  * {a.name} ({a.entity_id[:8]}…) aff={a.affinity} {reason}")


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
    candidates_raw = candidate or [
        "Cervejaria Ramiro",
        "The French Laundry",
    ]
    request = EvaluateRequest(
        city=city,
        city_center=LatLng(lat=lat, lon=lon),
        seed_queries=_parse_seeds(seed),
        candidates=[CandidateInput(name=n) for n in candidates_raw],
        fetch_alternatives=not no_alternatives,
    )
    result = asyncio.run(TasteGuardService().evaluate(request))

    if json_out:
        print(json.dumps(result.model_dump(), indent=2, default=str))
        return
    _print_result(result)


@app.command("demo")
def demo(
    city: str = typer.Option("Lisbon", help="City label"),
    lat: float = typer.Option(38.7223, help="City center latitude"),
    lon: float = typer.Option(-9.1393, help="City center longitude"),
    seed: Optional[list[str]] = typer.Option(
        None,
        "--seed",
        "-s",
        help="Persona seed as type:query. Repeatable.",
    ),
    persona: str = typer.Option(
        "Indie / artsy palate; prefers thoughtful local dining, not tourist traps.",
        help="Taste profile text for Gemini Flash (no tools).",
    ),
    max_rounds: int = typer.Option(3, help="Closed-set repair rounds"),
    n: int = typer.Option(5, help="How many Gemini recommendations to request"),
    json_out: bool = typer.Option(False, "--json", help="Print JSON history"),
) -> None:
    """Gemini Flash (no tools) → TasteGuard evaluate → closed-set repair loop."""
    from app.gemini_agent import GeminiConcierge

    async def _run():
        agent = GeminiConcierge()
        print("[bold]Unguarded baseline:[/bold] Gemini Flash, no tools")
        if not agent.enabled:
            print("[red]GEMINI_API_KEY is not set in .env — cannot run demo baseline.[/red]")
            raise typer.Exit(code=1)
        candidates = await agent.recommend(
            city=city, persona_description=persona, n=n
        )
        print(f"Gemini proposed {len(candidates)} places:")
        for c in candidates:
            print(f"  • {c.name} ({c.neighbourhood or '—'})")

        request = EvaluateRequest(
            city=city,
            city_center=LatLng(lat=lat, lon=lon),
            seed_queries=_parse_seeds(seed),
            candidates=candidates,
            fetch_alternatives=True,
        )
        service = TasteGuardService()
        final, history = await service.repair_until_pass(
            request,
            persona_description=persona,
            max_rounds=max_rounds,
        )
        return final, history, candidates

    final, history, unguarded = asyncio.run(_run())

    if json_out:
        print(
            json.dumps(
                {
                    "baseline": "Gemini Flash, no tools",
                    "unguarded": [c.model_dump() for c in unguarded],
                    "history": [h.model_dump() for h in history],
                    "final": final.model_dump(),
                },
                indent=2,
                default=str,
            )
        )
        return

    for i, snap in enumerate(history):
        label = "unguarded" if i == 0 else f"repair#{i}"
        _print_result(snap, label=label)
        print("")

    if final.policy_verdict == PolicyVerdict.PASS:
        print("[green]PASS[/green] after closed-set repair")
    else:
        print("[yellow]Still FAIL[/yellow] after repair rounds — see alternatives above")


if __name__ == "__main__":
    app()
