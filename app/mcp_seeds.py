"""Validate public MCP seed_queries shapes."""

from __future__ import annotations

from typing import Any

# Documented types used by TasteGuard presets / tool docs.
_ALLOWED_TYPE_PREFIXES = ("urn:entity:", "urn:tag")


def validate_mcp_seed_queries(
    seed_queries: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """Require query + types; reject undocumented shapes (e.g. {\"type\": \"artist\"})."""
    if not seed_queries:
        return []
    out: list[dict[str, str]] = []
    for i, raw in enumerate(seed_queries):
        if not isinstance(raw, dict):
            raise ValueError(
                f"seed_queries[{i}] must be an object with query and types "
                '(e.g. {"query": "Radiohead", "types": "urn:entity:artist"})'
            )
        if "type" in raw and "types" not in raw:
            raise ValueError(
                f"seed_queries[{i}]: use key \"types\" (not \"type\"), "
                'e.g. {"query": "Radiohead", "types": "urn:entity:artist"}'
            )
        query = str(raw.get("query") or "").strip()
        types = str(raw.get("types") or "").strip()
        if not query or not types:
            raise ValueError(
                f"seed_queries[{i}] requires non-empty query and types "
                '(e.g. {"query": "Radiohead", "types": "urn:entity:artist"})'
            )
        if not types.startswith(_ALLOWED_TYPE_PREFIXES):
            raise ValueError(
                f"seed_queries[{i}].types must start with urn:entity: or urn:tag "
                f"(got {types!r})"
            )
        out.append({"query": query[:120], "types": types[:80]})
    return out
