from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LatLng:
    lat: float
    lon: float


def haversine_km(a: LatLng, b: LatLng) -> float:
    r = 6371.0
    lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(h))


def extract_latlng(entity: dict[str, Any]) -> LatLng | None:
    """Best-effort coordinates from a Qloo place entity."""
    props = entity.get("properties") or {}
    loc = entity.get("location") or props.get("location") or {}

    for container in (loc, props, entity):
        if not isinstance(container, dict):
            continue
        for lat_k, lon_k in (("lat", "lon"), ("latitude", "longitude"), ("lat", "lng")):
            if lat_k in container and lon_k in container:
                try:
                    return LatLng(lat=float(container[lat_k]), lon=float(container[lon_k]))
                except (TypeError, ValueError):
                    pass
        geocode = container.get("geocode")
        if isinstance(geocode, dict) and "lat" in geocode:
            try:
                return LatLng(
                    lat=float(geocode["lat"]),
                    lon=float(geocode.get("lon", geocode.get("lng"))),
                )
            except (TypeError, ValueError):
                pass
        coord = container.get("coordinate") or container.get("coordinates")
        if isinstance(coord, dict) and "lat" in coord:
            try:
                return LatLng(
                    lat=float(coord["lat"]),
                    lon=float(coord.get("lon", coord.get("lng"))),
                )
            except (TypeError, ValueError):
                pass
        if isinstance(coord, (list, tuple)) and len(coord) >= 2:
            # GeoJSON-ish [lon, lat]
            try:
                return LatLng(lat=float(coord[1]), lon=float(coord[0]))
            except (TypeError, ValueError):
                pass
    return None


def extract_address(entity: dict[str, Any]) -> str | None:
    props = entity.get("properties") or {}
    for key in ("address", "formatted_address", "street_address"):
        val = props.get(key) or entity.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def extract_locality(entity: dict[str, Any]) -> str | None:
    props = entity.get("properties") or {}
    for key in ("locality", "city", "town", "municipality", "neighborhood"):
        val = props.get(key) or entity.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    loc = props.get("location") or entity.get("location") or {}
    if isinstance(loc, dict):
        for key in ("locality", "city", "neighborhood"):
            val = loc.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def latlon_param(point: LatLng) -> str:
    """Format for Qloo Search filter.location (must be lat,lon)."""
    return f"{point.lat},{point.lon}"
