"""Turns an observation + geography into a draft 311 request and a routing list. Deterministic; staff can edit."""
from typing import Any, Optional

from app.models import Observation, Source
from app.services.geo import GeoResult
from app.utils.constants import AGENCY_HANDLES, BORO_CODES, MAX_COMMUNITY_DISTRICT, SR_TYPES

AGENCY_FULL_NAMES = {
    "NYC DOT": "Department of Transportation",
    "NYC DSNY": "Department of Sanitation",
    "NYC Parks": "Department of Parks & Recreation",
    "NYC DEP": "Department of Environmental Protection",
    "NYC HPD": "Housing Preservation & Development",
    "NYPD": "NYPD (non-emergency)",
    "NYC DOB": "Department of Buildings",
    "NYC DOHMH": "Department of Health & Mental Hygiene",
    "MTA": "Metropolitan Transportation Authority (state agency, outside 311)",
    "NYC 311": "NYC 311 (general)",
}


def community_board_name(boro_cd: Optional[int]) -> Optional[str]:
    if not boro_cd:
        return None
    borough, num = BORO_CODES.get(boro_cd // 100), boro_cd % 100
    if not borough:
        return None
    if num > MAX_COMMUNITY_DISTRICT:
        return f"{borough} joint interest area {boro_cd} (park/airport, no community board)"
    return f"{borough} Community Board {num}"


def _agency(name: str, role: str, why: str, confidence: float) -> dict[str, Any]:
    return {"kind": "agency", "name": name, "detail": AGENCY_FULL_NAMES.get(name, name),
            "role": role, "why": why, "confidence": round(confidence, 2)}


def build_routing(obs: Observation, source: Source, geo: GeoResult, primary_agency: str) -> list[dict[str, Any]]:
    """Ordered list: who should act, who should know, and who the poster already addressed."""
    routes = [_agency(primary_agency, "owner", "311 complaint type owner", 0.9)]
    for cand in obs.agency_candidates or []:
        if cand["name"] != primary_agency and cand["confidence"] >= 0.5:
            routes.append(_agency(cand["name"], "secondary", "AI-suggested secondary agency", cand["confidence"]))

    borough = geo.borough or obs.borough
    board = community_board_name(geo.community_district)
    if board:
        routes.append({"kind": "community_board", "name": board, "detail": f"BoroCD {geo.community_district}",
                       "role": "notify", "why": f"Location falls in district {geo.community_district} ({geo.precision}-level match)",
                       "confidence": 0.85 if geo.precision == "address" else 0.6})
    if geo.council_district:
        routes.append({"kind": "council", "name": f"City Council District {geo.council_district}",
                       "detail": f"https://council.nyc.gov/district-{geo.council_district}/",
                       "role": "notify", "why": "Constituent services office for this location",
                       "confidence": 0.85 if geo.precision == "address" else 0.6})
    if borough:
        routes.append({"kind": "borough_president", "name": f"{borough} Borough President's Office",
                       "detail": "Borough-level escalation", "role": "cc", "why": "Borough of the reported location",
                       "confidence": 0.9 if geo.borough else 0.5})

    for handle in source.mentions or []:
        agency = AGENCY_HANDLES.get(handle)
        if agency:
            routes.append({"kind": "tagged", "name": f"@{handle}", "detail": AGENCY_FULL_NAMES.get(agency, agency),
                           "role": "tagged_by_poster", "why": "Poster tagged this account in the caption",
                           "confidence": 1.0})
    return routes


def draft_service_request(obs: Observation, source: Source, geo: GeoResult) -> dict[str, Any]:
    complaint_type, descriptor, agency = SR_TYPES.get(obs.topic, SR_TYPES["other"])
    top = (obs.agency_candidates or [{}])[0].get("name")
    if obs.topic == "other" and top:
        agency = top
    address = geo.label or obs.location_description
    quote = (obs.evidence or {}).get("quote")
    posted = source.posted_at.strftime("%b %d, %Y") if source.posted_at else "date unknown"
    lines = [
        obs.summary.strip(),
        f"Location as reported: {obs.location_description or 'not stated'}"
        + (f" ({obs.neighborhood}, {obs.borough})" if obs.neighborhood and obs.borough else ""),
    ]
    if quote:
        lines.append(f'Resident\'s words: "{quote}"')
    lines.append(
        f"Source: public {source.platform} video by @{source.creator_handle or 'unknown'} posted {posted}"
        + (f" — {source.post_url}" if source.post_url else "")
    )
    if obs.location_confidence < 0.5 or geo.precision != "address":
        lines.append("Note: exact location unconfirmed — verify before dispatch.")
    return {
        "complaint_type": complaint_type,
        "descriptor": descriptor,
        "agency": agency,
        "address": address,
        "latitude": geo.latitude,
        "longitude": geo.longitude,
        "community_district": geo.community_district,
        "council_district": geo.council_district,
        "description": "\n".join(lines),
        "routing": build_routing(obs, source, geo, agency),
    }
