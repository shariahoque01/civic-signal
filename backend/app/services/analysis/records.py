"""Normalized transcript records for analysis.

Every analysis works on `Record`, never on ORM rows, so it survives schema changes to `sources`.
`load_records()` reads the live DB when it has rows, else falls back to data/analysis_corpus.json.
"""
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

CORPUS_PATH = Path(__file__).resolve().parents[3] / "data" / "analysis_corpus.json"
MIN_DB_ROWS = 10  # below this the DB is a demo stub; the cached corpus is more useful

_LABELS = {
    "caption": "Caption",
    "location_tag": "Location tag on post",
    "on_screen": "On-screen text",
    "speech": r"Spoken \(TikTok captions\)|Spoken transcript|Captions",
}
_LABEL_LINE = re.compile(
    r"^(Caption|Location tag on post|On-screen text|Spoken \(TikTok captions\)|Spoken transcript|Captions|User caption):\s*",
    re.M,
)


@dataclass
class Record:
    id: str
    url: Optional[str] = None
    platform: str = "tiktok"
    handle: Optional[str] = None
    posted_at: Optional[datetime] = None
    caption: str = ""
    speech: str = ""
    on_screen: str = ""
    location_tag: Optional[str] = None
    hashtags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    language: Optional[str] = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    discovered_via: list[str] = field(default_factory=list)
    # Optional, filled from observations/service_requests when present in the DB.
    topic: Optional[str] = None
    borough: Optional[str] = None
    neighborhood: Optional[str] = None
    complaint_type: Optional[str] = None
    relevance: Optional[str] = None

    @property
    def text(self) -> str:
        """Everything the poster said or wrote, in one lowercase-able string."""
        parts = [self.caption, self.on_screen, self.speech]
        return "\n".join(p for p in parts if p)

    @property
    def has_speech(self) -> bool:
        return bool(self.speech.strip())

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d["posted_at"] = self.posted_at.isoformat() + "Z" if self.posted_at else None
        return d


def split_transcript(blob: str) -> dict[str, str]:
    """Split the labelled transcript blob ('Caption: ...\\nSpoken ...: ...') into its parts."""
    out: dict[str, str] = {}
    matches = list(_LABEL_LINE.finditer(blob or ""))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(blob)
        label, body = m.group(1), blob[m.end():end].strip()
        key = next((k for k, pat in _LABELS.items() if re.fullmatch(pat, label)), None)
        if key == "caption" or label == "User caption":
            key = "caption"
        if key:
            out[key] = (out.get(key, "") + " " + body).strip()
    if not matches and blob:
        out["speech"] = blob.strip()
    return out


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return [s for s in re.split(r"[,\s]+", v) if s]
    return [str(x).lower().lstrip("#@") for x in v] if isinstance(v, (list, tuple)) else []


def _as_dt(v: Any) -> Optional[datetime]:
    if v is None or isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def record_from_mapping(row: dict[str, Any]) -> Record:
    """Build a Record from a DB row or corpus dict, tolerating missing/extra/renamed columns."""
    g = lambda *keys: next((row[k] for k in keys if row.get(k) not in (None, "")), None)  # noqa: E731
    parts = split_transcript(g("transcript") or "")
    on_screen = g("on_screen_text", "on_screen")
    if isinstance(on_screen, str) and on_screen.lstrip().startswith("["):
        try:  # the DB stores this column as a JSON list
            on_screen = json.loads(on_screen)
        except ValueError:
            pass
    if isinstance(on_screen, (list, tuple)):
        on_screen = " / ".join(on_screen)
    return Record(
        id=str(g("id", "url", "post_url") or ""),
        url=g("post_url", "url"),
        platform=g("platform") or "tiktok",
        handle=g("creator_handle", "handle"),
        posted_at=_as_dt(g("posted_at")),
        caption=g("caption") or parts.get("caption", ""),
        speech=g("speech_text", "speech") or parts.get("speech", ""),
        on_screen=on_screen or parts.get("on_screen", ""),
        location_tag=g("location_tag") or parts.get("location_tag"),
        hashtags=_as_list(g("hashtags")),
        mentions=_as_list(g("mentions")),
        language=g("speech_language", "language"),
        views=_int(g("view_count", "views")),
        likes=_int(g("engagement", "likes", "like_count")),
        comments=_int(g("comment_count", "comments")),
        shares=_int(g("share_count", "shares")),
        discovered_via=_as_list(g("discovered_via")),
        topic=g("topic"),
        borough=g("borough"),
        neighborhood=g("neighborhood"),
        complaint_type=g("complaint_type"),
        relevance=g("relevance"),
    )


def load_from_db(engine) -> list[Record]:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "sources" not in tables:
        return []
    with engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM sources"))]
        if not rows:
            return []
        obs_by_source: dict[str, dict] = {}
        if "observations" in tables:
            cols = {c["name"] for c in insp.get_columns("observations")}
            want = [c for c in ("id", "source_id", "topic", "borough", "neighborhood") if c in cols]
            if "source_id" in want:
                for r in conn.execute(text(f"SELECT {', '.join(want)} FROM observations")):
                    obs_by_source.setdefault(r._mapping["source_id"], dict(r._mapping))
        sr_by_obs: dict[str, str] = {}
        if "service_requests" in tables:
            cols = {c["name"] for c in insp.get_columns("service_requests")}
            if {"observation_id", "complaint_type"} <= cols:
                for r in conn.execute(text("SELECT observation_id, complaint_type FROM service_requests")):
                    sr_by_obs[r[0]] = r[1]
    out = []
    for row in rows:
        obs = obs_by_source.get(row.get("id"), {})
        merged = {**row, **{k: v for k, v in obs.items() if k in ("topic", "borough", "neighborhood")}}
        if obs.get("id") in sr_by_obs:
            merged["complaint_type"] = sr_by_obs[obs["id"]]
        out.append(record_from_mapping(merged))
    return out


def load_from_corpus(path: Path = CORPUS_PATH) -> list[Record]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [record_from_mapping(r) for r in data.get("records", []) if "error" not in r]


def dedupe(records: Iterable[Record]) -> list[Record]:
    seen: dict[str, Record] = {}
    for r in records:
        key = (r.url or r.id).split("?")[0]
        seen.setdefault(key, r)
    return list(seen.values())


def load_records(prefer: str = "auto") -> tuple[list[Record], str]:
    """Returns (records, source_label). prefer: 'auto' | 'db' | 'corpus'."""
    db_records: list[Record] = []
    if prefer in ("auto", "db"):
        try:
            from app.database import engine

            db_records = load_from_db(engine)
        except Exception as exc:  # noqa: BLE001 - DB may be mid-rebuild by another process
            logger.warning("Insights: DB read failed, falling back to corpus: %s", exc)
    if prefer == "db" or (prefer == "auto" and len(db_records) >= MIN_DB_ROWS):
        return dedupe(db_records), "database"
    corpus = load_from_corpus()
    if corpus:
        return dedupe(corpus), "corpus"
    return dedupe(db_records), "database"
