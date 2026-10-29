"""Supported city centres for MCP when lat/lon are omitted."""

from __future__ import annotations

CITY_CENTERS: dict[str, tuple[float, float]] = {
    "lisbon": (38.7223, -9.1393),
    "new york": (40.7128, -74.0060),
    "nyc": (40.7128, -74.0060),
}


def resolve_mcp_coords(
    city: str,
    lat: float | None,
    lon: float | None,
) -> tuple[float, float]:
    """Return (lat, lon). Unknown cities require explicit coordinates."""
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    if lat is not None or lon is not None:
        raise ValueError("Pass both lat and lon, or omit both for a supported city")
    key = (city or "").strip().lower()
    if key in CITY_CENTERS:
        return CITY_CENTERS[key]
    raise ValueError(
        f"Unknown city {city!r}; pass lat and lon "
        "(supported defaults: Lisbon, New York)"
    )
