"""Geocoding (NYC Planning GeoSearch) and district lookup (NYC Planning ArcGIS layers). Keyless, public."""
import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.utils.constants import ARCGIS_BASE, BORO_CODES, GEOSEARCH_URL

logger = logging.getLogger(__name__)
TIMEOUT = 10
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "civic-signal/0.1 (NYC civic intake prototype)"
INTERSECTION_RE = re.compile(r"\s(&|and|at|/)\s|\bcorner of\b", re.IGNORECASE)
ABBREVIATIONS = [
    (r"\bave?\b\.?", "Avenue"), (r"\bst\b\.?", "Street"), (r"\bblvd\b\.?", "Boulevard"),
    (r"\bpkwy\b\.?", "Parkway"), (r"\brd\b\.?", "Road"), (r"\bpl\b\.?", "Place"),
    (r"\be\.?(?= \d)", "East"), (r"\bw\.?(?= \d)", "West"), (r"\b(\d+)(st|nd|rd|th)\b", r"\1\2"),
    (r"\s+(and|at|/)\s+", " & "), (r"\bcorner of\s+", ""),
]
_last_nominatim = 0.0  # Nominatim usage policy: max 1 request/second


@dataclass
class GeoResult:
    label: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    community_district: Optional[int] = None  # BoroCD, e.g. 314 = Brooklyn CB 14
    council_district: Optional[int] = None
    borough: Optional[str] = None
    precision: str = "none"  # address | area | none


async def _geosearch(client: httpx.AsyncClient, text: str) -> Optional[dict]:
    resp = await client.get(GEOSEARCH_URL, params={"text": text, "size": 1})
    resp.raise_for_status()
    features = resp.json().get("features") or []
    return features[0] if features else None


async def _nominatim(client: httpx.AsyncClient, text: str) -> Optional[dict]:
    """Returns a GeoJSON-like feature so callers can treat both geocoders the same."""
    global _last_nominatim
    wait = 1.0 - (time.monotonic() - _last_nominatim)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_nominatim = time.monotonic()
    resp = await client.get(
        NOMINATIM_URL, params={"q": text, "format": "json", "limit": 1, "countrycodes": "us"},
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return None
    return {
        "geometry": {"coordinates": [float(rows[0]["lon"]), float(rows[0]["lat"])]},
        "properties": {"label": rows[0].get("display_name")},
    }


def normalize_street_text(text: str) -> str:
    """'Church Ave and Flatbush Ave' -> 'Church Avenue & Flatbush Avenue' (Nominatim needs full names)."""
    for pattern, repl in ABBREVIATIONS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


async def _district(client: httpx.AsyncClient, layer: str, field: str, lon: float, lat: float) -> Optional[int]:
    resp = await client.get(
        f"{ARCGIS_BASE}/{layer}/FeatureServer/0/query",
        params={
            "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": field,
            "returnGeometry": "false", "f": "json",
        },
    )
    resp.raise_for_status()
    features = resp.json().get("features") or []
    value = features[0]["attributes"].get(field) if features else None
    return int(value) if value is not None else None


async def locate(
    location: Optional[str], neighborhood: Optional[str], borough: Optional[str]
) -> GeoResult:
    """Best-effort: try the specific location, then neighborhood. Never raises; returns precision='none' on failure."""
    suffix = ", ".join(p for p in (borough, "New York, NY") if p)
    attempts = []
    if location:
        text = f"{location}, {suffix}"
        # GeoSearch is best at street addresses; intersections and landmarks go to Nominatim.
        if re.match(r"^\d+[A-Za-z-]*\s", location) and not INTERSECTION_RE.search(location):
            attempts += [(_geosearch, text, "address"), (_nominatim, text, "address")]
        else:
            full = normalize_street_text(location)
            attempts += [
                (_nominatim, f"{full}, {suffix}", "address"),
                (_nominatim, f"{full}, {borough or 'New York'}", "address"),
                (_geosearch, text, "address"),
            ]
    if neighborhood:
        attempts.append((_nominatim, f"{neighborhood}, {suffix}", "area"))
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for geocoder, text, precision in attempts:
                feature = await geocoder(client, text)
                if not feature:
                    continue
                lon, lat = feature["geometry"]["coordinates"]
                cd = await _district(client, "NYC_Community_Districts", "BoroCD", lon, lat)
                cc = await _district(client, "NYC_City_Council_Districts", "CounDist", lon, lat)
                if cd is None:  # geocoder matched something outside NYC
                    continue
                return GeoResult(
                    label=feature["properties"].get("label"), latitude=lat, longitude=lon,
                    community_district=cd, council_district=cc,
                    borough=BORO_CODES.get(cd // 100), precision=precision,
                )
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Geocoding failed for %r: %s", location or neighborhood, exc)
    return GeoResult()
