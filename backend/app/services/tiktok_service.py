"""TikTok public-page reader. One request yields caption, hashtags, mentions, location tag (POI),
on-screen text stickers, stats, and TikTok's own speech captions (ASR) — no login or API key.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services.video_service import ExtractionError, PostMetadata, _vtt_to_text

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
DATA_RE = re.compile(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S)
VIDEO_ID_RE = re.compile(r"/video/(\d+)")


def posted_at_from_id(url: str) -> Optional[datetime]:
    """TikTok IDs are snowflakes: the top 32 bits are the Unix post time. Lets us date-filter for free."""
    m = VIDEO_ID_RE.search(url)
    if not m:
        return None
    return datetime.fromtimestamp(int(m.group(1)) >> 32, timezone.utc).replace(tzinfo=None)


@dataclass
class TikTokPost:
    meta: PostMetadata
    speech: str = ""
    speech_language: Optional[str] = None
    location_tag: Optional[str] = None  # creator-attached place, most reliable location signal
    on_screen_text: list[str] = field(default_factory=list)
    comment_count: int = 0
    share_count: int = 0


def _item(html: str) -> dict[str, Any]:
    m = DATA_RE.search(html)
    if not m:
        raise ExtractionError("TikTok page had no video data (removed, private, or blocked)")
    scope = json.loads(m.group(1)).get("__DEFAULT_SCOPE__", {})
    item = scope.get("webapp.video-detail", {}).get("itemInfo", {}).get("itemStruct")
    if not item:
        raise ExtractionError("TikTok video not available")
    return item


def _poi(item: dict[str, Any]) -> Optional[str]:
    poi = item.get("poi") or item.get("poiInfo") or {}
    parts = [poi.get(k) for k in ("name", "address", "city") if poi.get(k)]
    return ", ".join(dict.fromkeys(parts)) or None


def _stickers(item: dict[str, Any]) -> list[str]:
    texts = []
    for sticker in item.get("stickersOnItem") or []:
        texts += [t.strip() for t in sticker.get("stickerText") or [] if t and t.strip()]
    return texts


async def fetch_post(url: str) -> TikTokPost:
    try:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            item = _item(resp.text)
            speech, lang = "", None
            subs = sorted(
                item.get("video", {}).get("subtitleInfos") or [],
                key=lambda s: s.get("Source") != "ASR",  # prefer original-language ASR over machine translation
            )
            for sub in subs:
                if sub.get("Format") == "webvtt" and sub.get("Url"):
                    try:
                        vtt = await client.get(sub["Url"])
                        vtt.raise_for_status()
                        speech, lang = _vtt_to_text(vtt.text), (sub.get("LanguageCodeName") or "")[:2] or None
                        break
                    except httpx.HTTPError as exc:
                        logger.warning("TikTok caption fetch failed: %s", exc)
    except httpx.HTTPError as exc:
        raise ExtractionError(f"Could not load TikTok page: {exc}") from exc

    extras = item.get("textExtra") or []
    stats = item.get("statsV2") or item.get("stats") or {}
    created = item.get("createTime")
    meta = PostMetadata(
        creator_handle=(item.get("author") or {}).get("uniqueId"),
        posted_at=datetime.fromtimestamp(int(created), timezone.utc).replace(tzinfo=None) if created else posted_at_from_id(url),
        view_count=int(stats.get("playCount") or 0),
        like_count=int(stats.get("diggCount") or 0),
        caption=item.get("desc") or "",
        mentions=list(dict.fromkeys(t["userUniqueId"].lower() for t in extras if t.get("userUniqueId"))),
        hashtags=list(dict.fromkeys(t["hashtagName"].lower() for t in extras if t.get("hashtagName"))),
        thumbnail_url=(item.get("video") or {}).get("cover"),
    )
    return TikTokPost(
        meta=meta, speech=speech, speech_language=lang, location_tag=_poi(item),
        on_screen_text=_stickers(item),
        comment_count=int(stats.get("commentCount") or 0), share_count=int(stats.get("shareCount") or 0),
    )


def as_transcript(post: TikTokPost) -> str:
    """Compose the text the extractor sees, labelling each source so location evidence is traceable."""
    parts = []
    if post.meta.caption:
        parts.append(f"Caption: {post.meta.caption}")
    if post.location_tag:
        parts.append(f"Location tag on post: {post.location_tag}")
    if post.on_screen_text:
        parts.append("On-screen text: " + " / ".join(post.on_screen_text))
    if post.speech:
        parts.append(f"Spoken (TikTok captions): {post.speech}")
    return "\n".join(parts)
