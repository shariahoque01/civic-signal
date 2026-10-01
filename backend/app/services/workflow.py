"""'Mamdani, fix this' pipeline: post URL -> metadata filter -> extraction -> geocode -> 311 draft + routing."""
import logging
import re
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Observation, ServiceRequest, Source, _now
from app.services import gemini_service, geo, heuristics, routing, tiktok_service, video_service
from app.utils.constants import (
    DEFAULT_LANGUAGE, DEFAULT_WINDOW_DAYS, FIX_KEYWORDS, MAYOR_HANDLES, MAYOR_KEYWORDS, NON_NYC_PLACES,
    NYC_LOCATION_TAG_RE, NYC_SIGNAL_RE, RELEVANCE_FIX, RELEVANCE_MAYOR, RELEVANCE_OUTSIDE, RELEVANCE_UNRELATED,
)

logger = logging.getLogger(__name__)
ACTIONABLE_TYPES = ("issue", "request", "idea")


def matches_query(meta: video_service.PostMetadata, transcript: str) -> tuple[bool, bool]:
    """(tags the mayor, asks to fix something). #mamdanifixthis counts as both."""
    text = f"{meta.caption}\n{transcript}".lower()
    tags = {h.replace("_", "") for h in meta.hashtags}
    combo = any(("mamdani" in t or "zohran" in t) and "fix" in t for t in tags)
    mayor = combo or any(h in meta.mentions for h in MAYOR_HANDLES) or any(k in text for k in MAYOR_KEYWORDS)
    fix = combo or any(k in text for k in FIX_KEYWORDS) or any("fix" in t for t in tags)
    return mayor, fix


def relevance(meta: video_service.PostMetadata, transcript: str, location_tag: Optional[str] = None) -> str:
    """Corpus label: fix_request (tags the mayor + asks for a fix, about NYC), outside_nyc (a fix request
    about another city or country), mayor_related, or unrelated."""
    mayor, fix = matches_query(meta, transcript)
    if mayor and fix:
        return RELEVANCE_OUTSIDE if is_outside_nyc(f"{meta.caption}\n{transcript}", location_tag) else RELEVANCE_FIX
    return RELEVANCE_MAYOR if mayor else RELEVANCE_UNRELATED


def outside_nyc(text: str) -> str | None:
    low = text.lower()
    for place in NON_NYC_PLACES:
        if any(ch in place for ch in "\\[(?"):  # already a regex
            pattern = (r"\b" if place[0].isalnum() else "") + place
        else:
            pattern = rf"\b{re.escape(place)}\b"
        m = re.search(pattern, low)
        if m:
            return m.group(0).lstrip("#")
    return None


def is_outside_nyc(text: str, location_tag: Optional[str] = None) -> bool:
    """Conservative: the post names a non-NYC place (in text, or as its location tag) and nothing in its
    non-hashtag text points to NYC. "#nyc" alone is not NYC evidence; nearly every trend post carries it."""
    tag_elsewhere = bool(location_tag) and not re.search(NYC_LOCATION_TAG_RE, location_tag.lower())
    if not (tag_elsewhere or outside_nyc(text)):
        return False
    plain = re.sub(r"#\w+", " ", text.lower())
    plain = re.sub(r"location tag on post:.*", " ", plain)  # judged separately above
    return not re.search(NYC_SIGNAL_RE, plain) and not (location_tag and not tag_elsewhere)


async def _fetch(url: str) -> tuple[str, str, video_service.PostMetadata, dict[str, Any]]:
    """Returns (platform, labelled transcript, metadata, extra Source fields)."""
    if video_service.validate_url(url, "tiktok"):
        post = await tiktok_service.fetch_post(url)
        extra = {
            "comment_count": post.comment_count, "share_count": post.share_count,
            "location_tag": post.location_tag, "speech_language": post.speech_language,
            "has_speech": bool(post.speech.strip()), "speech_text": post.speech or None,
            "on_screen_text": post.on_screen_text,
        }
        return "tiktok", tiktok_service.as_transcript(post), post.meta, extra
    if video_service.validate_url(url, "instagram"):
        bundle = await video_service.get_video_bundle(url, "instagram")
        return "instagram", bundle.transcript, bundle.meta, {"has_speech": bool(bundle.transcript.strip())}
    raise video_service.ExtractionError("Only TikTok and Instagram URLs are supported")


async def process_url(
    db: Session, url: str, window_days: Optional[int] = DEFAULT_WINDOW_DAYS,
    discovered_via: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Fetch one post and store it. Every fetched post becomes a Source with a relevance label; only
    fix requests go on to extraction, an Observation and (if actionable) a 311 draft.
    window_days=None stores posts of any age (corpus building); the API passes a window."""
    url = url.strip().split("?")[0]
    via = list(discovered_via or [])
    existing = db.scalar(select(Source).where(Source.post_url == url))
    if existing:
        merged = list(dict.fromkeys((existing.discovered_via or []) + via))
        if merged != (existing.discovered_via or []):
            existing.discovered_via = merged
            db.commit()
        return {"url": url, "status": "skipped", "reason": "already processed"}

    # Free date check for TikTok before any network call.
    posted = tiktok_service.posted_at_from_id(url)
    cutoff = _now() - timedelta(days=window_days) if window_days else None
    if cutoff and posted and posted < cutoff:
        return {"url": url, "status": "skipped", "reason": f"posted {posted:%Y-%m-%d}, outside {window_days}-day window"}

    try:
        platform, transcript, meta, extra = await _fetch(url)
    except video_service.ExtractionError as exc:
        return {"url": url, "status": "error", "reason": str(exc)}
    if cutoff and meta.posted_at and meta.posted_at < cutoff:
        return {"url": url, "status": "skipped", "reason": f"posted {meta.posted_at:%Y-%m-%d}, outside window"}

    label = relevance(meta, transcript, extra.get("location_tag"))
    source = Source(
        platform=platform, post_url=url, transcript=transcript, caption=meta.caption,
        language=extra.get("speech_language") or DEFAULT_LANGUAGE, engagement=meta.like_count,
        creator_handle=meta.creator_handle, posted_at=meta.posted_at, view_count=meta.view_count,
        mentions=meta.mentions, hashtags=meta.hashtags, thumbnail_url=meta.thumbnail_url,
        relevance=label, discovered_via=via, **extra,
    )
    if label != RELEVANCE_FIX:
        db.add(source)
        db.commit()
        why = ("fix request about a place outside NYC" if label == RELEVANCE_OUTSIDE
               else "does not tag the mayor with a fix request")
        return {"url": url, "status": "stored", "relevance": label, "source_id": source.id,
                "reason": f"{why}; transcript stored for the corpus"}
    return await extract_and_draft(db, source, extra)


async def extract_and_draft(db: Session, source: Source, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Fix request -> Observation and, when actionable in NYC, a drafted 311 ServiceRequest. Commits."""
    url, transcript, label = source.post_url, source.transcript, source.relevance
    extra = extra or {"has_speech": source.has_speech, "on_screen_text": source.on_screen_text}
    if gemini_service.is_configured():
        try:
            extracted = await gemini_service.extract_observation(transcript)
        except gemini_service.GeminiError as exc:
            logger.warning("Gemini failed, using keyword draft: %s", exc)
            extracted = heuristics.extract(transcript)
    else:
        extracted = heuristics.extract(transcript)

    source.language = extracted["language"]
    obs = Observation(source=source, **extracted)
    db.add_all([source, obs])
    db.flush()  # assign ids

    result = {"url": url, "status": "processed", "relevance": label, "source_id": source.id,
              "observation_id": obs.id, "topic": obs.topic, "type": obs.type}
    elsewhere = outside_nyc(transcript)
    has_speech = bool(extra.get("has_speech")) or bool(extra.get("on_screen_text"))
    if elsewhere:
        note = f"Outside NYC ({elsewhere}) — not routable to NYC 311"
    elif obs.topic == "other" and not has_speech:
        note = "Visual-only request (no speech or on-screen text) — watch the video to identify the issue"
    else:
        note = None
    if note:
        obs.evidence = {**(obs.evidence or {}), "note": note}
        result["note"] = note
    elif obs.type in ACTIONABLE_TYPES and obs.topic != "other":
        where = await geo.locate(obs.location_description, obs.neighborhood, obs.borough)
        draft = routing.draft_service_request(obs, source, where)
        sr = ServiceRequest(observation=obs, **draft)
        db.add(sr)
        db.flush()
        result["service_request_id"] = sr.id
    if "note" not in result and "service_request_id" not in result:
        result["note"] = "not an actionable city-service issue (commentary, news, or unclear); no 311 drafted"
    db.commit()
    return result
