"""Content extraction: yt-dlp for TikTok/Instagram, Gemini for local video files."""
import asyncio
import logging
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
import yt_dlp

from app.config import get_settings
from app.services import gemini_service
from app.utils.constants import DEFAULT_LANGUAGE, MAX_AUDIO_SECONDS, PLATFORM_HOSTS

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    pass


@dataclass
class PostMetadata:
    creator_handle: Optional[str] = None
    posted_at: Optional[datetime] = None  # naive UTC
    view_count: int = 0
    like_count: int = 0
    caption: str = ""
    mentions: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    thumbnail_url: Optional[str] = None


@dataclass
class VideoBundle:
    transcript: str
    language: str
    engagement: int
    meta: PostMetadata


MENTION_RE = re.compile(r"@([A-Za-z0-9_.]{2,30})")
HASHTAG_RE = re.compile(r"#(\w{2,60})")


def parse_metadata(info: dict[str, Any]) -> PostMetadata:
    """Pull public post metadata out of a yt-dlp info dict."""
    caption = info.get("description") or info.get("title") or ""
    ts = info.get("timestamp")
    posted = datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None) if ts else None
    if posted is None and info.get("upload_date"):
        try:
            posted = datetime.strptime(info["upload_date"], "%Y%m%d")
        except ValueError:
            posted = None
    handle = info.get("channel") or info.get("uploader_id") or info.get("uploader")
    return PostMetadata(
        creator_handle=str(handle).lstrip("@") if handle else None,
        posted_at=posted,
        view_count=int(info.get("view_count") or 0),
        like_count=int(info.get("like_count") or 0),
        caption=caption,
        mentions=list(dict.fromkeys(m.rstrip(".").lower() for m in MENTION_RE.findall(caption))),
        hashtags=list(dict.fromkeys(h.lower() for h in HASHTAG_RE.findall(caption))),
        thumbnail_url=info.get("thumbnail"),
    )


async def fetch_metadata(url: str) -> tuple[PostMetadata, dict[str, Any]]:
    """Cheap metadata-only fetch, used to filter posts before any AI processing."""
    info = await asyncio.to_thread(_fetch_info, url)
    return parse_metadata(info), info


def validate_url(url: str, platform: str) -> bool:
    hosts = PLATFORM_HOSTS.get(platform)
    if not hosts:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and any(host == h or host.endswith("." + h) for h in hosts)


def resolve_upload_path(file_path: str) -> Path:
    """Only allow files inside the configured upload directory."""
    base = get_settings().upload_dir.resolve()
    candidate = Path(file_path)
    candidate = (candidate if candidate.is_absolute() else base / candidate).resolve()
    if not candidate.is_relative_to(base):
        raise ExtractionError(f"file_path must be inside the upload directory ({base})")
    if not candidate.is_file():
        raise ExtractionError("Uploaded file not found")
    return candidate


def _vtt_to_text(vtt: str) -> str:
    lines: list[str] = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line or line.startswith(("WEBVTT", "NOTE", "Kind:", "Language:")) or "-->" in line or line.isdigit():
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if not lines or lines[-1] != line:
            lines.append(line)
    return " ".join(lines)


def _fetch_info(url: str) -> dict[str, Any]:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False) or {}
    except yt_dlp.utils.DownloadError as exc:
        raise ExtractionError(f"Could not read video (private, removed, or unsupported): {exc}") from exc


async def _subtitle_text(info: dict[str, Any]) -> tuple[str, Optional[str]]:
    for key in ("subtitles", "automatic_captions"):
        for lang, formats in (info.get(key) or {}).items():
            for fmt in formats:
                if fmt.get("ext") == "vtt" and fmt.get("url"):
                    try:
                        async with httpx.AsyncClient(timeout=15) as client:
                            resp = await client.get(fmt["url"])
                            resp.raise_for_status()
                        return _vtt_to_text(resp.text), lang.split("-")[0]
                    except httpx.HTTPError as exc:
                        logger.warning("Subtitle fetch failed: %s", exc)
    return "", None


def _download_audio(url: str, out_dir: str) -> Path:
    """Download the smallest audio-bearing stream into out_dir (no re-encode, so ffmpeg is not required)."""
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "format": "bestaudio/worst", "outtmpl": f"{out_dir}/audio.%(ext)s",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = list(Path(out_dir).glob("audio.*"))
    if not files:
        raise ExtractionError("Audio download produced no file")
    return files[0]


async def _spoken_text(url: str, info: dict[str, Any]) -> str:
    """Best-effort speech transcript; returns '' on any failure so callers fall back to the caption."""
    duration = info.get("duration") or 0
    if duration > MAX_AUDIO_SECONDS:
        logger.info("Skipping audio transcription: %ss exceeds limit", duration)
        return ""
    try:
        with tempfile.TemporaryDirectory(prefix="civic_audio_") as tmp:  # deleted on exit
            audio = await asyncio.to_thread(_download_audio, url, tmp)
            text = await gemini_service.transcribe_video(audio, gemini_service.SPEECH_ONLY_PROMPT)
    except Exception as exc:  # yt-dlp / Gemini failures must not block caption-based extraction
        logger.warning("Audio transcription failed, using caption only: %s", exc)
        return ""
    text = text.strip()
    return "" if gemini_service.NO_SPEECH_MARKER in text else text


async def get_video_bundle(
    url: Optional[str], platform: str, file_path: Optional[str] = None,
    info: Optional[dict[str, Any]] = None,
) -> VideoBundle:
    """Transcript plus post metadata. Pass `info` to reuse an earlier metadata fetch."""
    if platform == "upload" or (file_path and not url):
        if not file_path:
            raise ExtractionError("file_path is required for uploads")
        path = resolve_upload_path(file_path)
        try:
            transcript = await gemini_service.transcribe_video(path)
        except gemini_service.GeminiError as exc:
            raise ExtractionError(str(exc)) from exc
        return VideoBundle(transcript, DEFAULT_LANGUAGE, 0, PostMetadata())

    if not url:
        raise ExtractionError("url is required")
    if info is None:
        info = await asyncio.to_thread(_fetch_info, url)
    subs, lang = await _subtitle_text(info)
    parts = [p for p in (info.get("title"), info.get("description")) if p]
    if subs:
        parts.append(f"Captions: {subs}")
    if gemini_service.is_configured():
        speech = await _spoken_text(url, info)
        if speech:
            parts.append(f"Spoken transcript: {speech}")
    transcript = "\n".join(dict.fromkeys(parts)).strip()  # dedupe title==description
    if not transcript:
        raise ExtractionError("No text (captions, title, or description) available for this video")
    meta = parse_metadata(info)
    return VideoBundle(transcript, lang or info.get("language") or DEFAULT_LANGUAGE, meta.like_count, meta)


async def get_video_content(
    url: Optional[str], platform: str, file_path: Optional[str] = None
) -> tuple[str, str, int]:
    """Return (transcript_text, language_code, engagement)."""
    bundle = await get_video_bundle(url, platform, file_path)
    return bundle.transcript, bundle.language, bundle.engagement
