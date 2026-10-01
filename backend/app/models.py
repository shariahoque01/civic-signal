import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.constants import DEFAULT_LANGUAGE, ID_PREFIXES


def _now() -> datetime:
    """Naive UTC timestamp (SQLite drops tzinfo anyway)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_id(kind: str) -> str:
    return ID_PREFIXES[kind] + uuid.uuid4().hex[:12]


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _new_id("source"))
    platform: Mapped[str] = mapped_column(String)
    post_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    transcript: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String, default=DEFAULT_LANGUAGE)
    engagement: Mapped[int] = mapped_column(Integer, default=0)
    # Public post metadata (handle only, no profile data).
    creator_handle: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    mentions: Mapped[list[str]] = mapped_column(JSON, default=list)
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Corpus fields: every fetched video is stored, fix request or not (see constants.RELEVANCE_LABELS).
    relevance: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    discovered_via: Mapped[list[str]] = mapped_column(JSON, default=list)  # e.g. ["#mamdanifixthis", "manual"]
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    location_tag: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    speech_language: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    has_speech: Mapped[bool] = mapped_column(Boolean, default=False)
    speech_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # ASR captions only
    on_screen_text: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)

    observations: Mapped[list["Observation"]] = relationship(back_populates="source")


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _new_id("observation"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    type: Mapped[str] = mapped_column(String, index=True)
    topic: Mapped[str] = mapped_column(String, index=True)
    summary: Mapped[str] = mapped_column(Text)
    location_description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    borough: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    neighborhood: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    location_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    agency_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    urgency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    language: Mapped[str] = mapped_column(String, default=DEFAULT_LANGUAGE)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="new", index=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_agency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    final_priority: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    source: Mapped[Source] = relationship(back_populates="observations")
    service_request: Mapped[Optional["ServiceRequest"]] = relationship(back_populates="observation", uselist=False)


class ServiceRequest(Base):
    """A drafted 311 request. Drafts are never auto-filed; staff file them and record the SR number."""

    __tablename__ = "service_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _new_id("service_request"))
    observation_id: Mapped[str] = mapped_column(ForeignKey("observations.id"), unique=True, index=True)
    complaint_type: Mapped[str] = mapped_column(String)
    descriptor: Mapped[str] = mapped_column(String)
    agency: Mapped[str] = mapped_column(String)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    community_district: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    council_district: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    routing: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="draft", index=True)
    sr_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    observation: Mapped[Observation] = relationship(back_populates="service_request")


class CivicSignal(Base):
    __tablename__ = "civic_signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _new_id("signal"))
    title: Mapped[str] = mapped_column(String)
    topic: Mapped[str] = mapped_column(String, index=True)
    borough: Mapped[str] = mapped_column(String, index=True)
    agency_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    observation_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_source_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trend: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
