from collections import defaultdict
from typing import Any

from app.models import Observation
from app.utils.constants import MIN_SIGNAL_GROUP_SIZE, UNKNOWN_BOROUGH


def group_observations(observations: list[Observation]) -> dict[tuple[str, str], list[Observation]]:
    groups: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        groups[(obs.topic, obs.borough or UNKNOWN_BOROUGH)].append(obs)
    return groups


def _merge_agencies(group: list[Observation]) -> list[dict[str, Any]]:
    scores: dict[str, list[float]] = defaultdict(list)
    for obs in group:
        for cand in obs.agency_candidates or []:
            scores[cand["name"]].append(cand["confidence"])
    merged = [{"name": n, "confidence": round(sum(v) / len(v), 2)} for n, v in scores.items()]
    return sorted(merged, key=lambda a: a["confidence"], reverse=True)


def aggregate_observations_simple(observations: list[Observation]) -> list[dict[str, Any]]:
    """Group by (topic, borough); keep groups with 2+ observations."""
    signals = []
    for (topic, borough), group in group_observations(observations).items():
        if len(group) < MIN_SIGNAL_GROUP_SIZE:
            continue
        signals.append({
            "title": f"{topic.replace('_', ' ').title()} in {borough}",
            "topic": topic,
            "borough": borough,
            "agency_candidates": _merge_agencies(group),
            "observation_ids": [o.id for o in group],
            "observation_count": len(group),
            "unique_source_count": len({o.source_id for o in group}),
            "confidence": round(sum(o.confidence for o in group) / len(group), 2),
        })
    return signals
