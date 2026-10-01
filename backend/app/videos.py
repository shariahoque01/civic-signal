"""/api/videos: every ingested video (not just 311 cases) for the "This week" page.

Reads Source columns defensively: the discovery pipeline may add fields (relevance, discovered_via,
comment_count, ...) and this endpoint passes through whatever exists.
"""
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Source, _now
from app.services import routing

router = APIRouter(prefix="/api/videos", tags=["videos"])
OPTIONAL_FIELDS = ("relevance", "discovered_via", "comment_count", "share_count", "location_tag", "speech_language", "has_speech")


def _video(src: Source) -> dict[str, Any]:
    obs = src.observations[0] if src.observations else None
    sr = obs.service_request if obs else None
    out = {
        "id": src.id, "platform": src.platform, "url": src.post_url, "handle": src.creator_handle,
        "posted_at": src.posted_at.isoformat() + "Z" if src.posted_at else None,
        "views": src.view_count or 0, "likes": src.engagement or 0, "caption": src.caption or "",
        "hashtags": src.hashtags or [], "mentions": src.mentions or [], "language": src.language,
        "transcript": src.transcript, "thumbnail_url": src.thumbnail_url,
        "observation": None if obs is None else {
            "id": obs.id, "type": obs.type, "topic": obs.topic, "summary": obs.summary,
            "quote": (obs.evidence or {}).get("quote"), "note": (obs.evidence or {}).get("note"),
            "borough": obs.borough, "neighborhood": obs.neighborhood, "confidence": obs.confidence,
        },
        "service_request": None if sr is None else {
            "id": sr.id, "complaint_type": sr.complaint_type, "agency": sr.agency, "status": sr.status,
            "community_board": routing.community_board_name(sr.community_district),
        },
    }
    for name in OPTIONAL_FIELDS:
        if hasattr(src, name):
            out[name] = getattr(src, name)
    if "relevance" not in out:  # older schema: infer from whether it became an observation
        out["relevance"] = "fix_request" if obs else "other"
    return out


@router.get("")
async def list_videos(
    days: Optional[int] = Query(7, ge=1, le=365, description="Only videos posted in the last N days"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    q = select(Source).order_by(Source.posted_at.desc().nullslast())
    if days:
        q = q.where(Source.posted_at >= _now() - timedelta(days=days))
    rows = db.scalars(q).all()
    return {"total": len(rows), "days": days, "videos": [_video(s) for s in rows]}
