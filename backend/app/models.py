import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
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
