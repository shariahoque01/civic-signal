from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.models import CivicSignal, Observation
from app.utils.constants import LOW_CONFIDENCE_THRESHOLD

Platform = Literal["tiktok", "instagram", "upload"]
ObservationType = Literal["issue", "request", "idea", "praise", "information", "other"]
Topic = Literal[
    "streetlights", "transportation", "trash", "rats", "parks", "sidewalks",
    "roads", "public_transit", "housing", "public_safety", "water", "noise",
    "construction", "accessibility", "public_facilities", "other",
]
Borough = Literal["Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"]
Urgency = Literal["low", "medium", "high"]
Status = Literal["new", "reviewed", "rejected"]
Priority = Literal["low", "medium", "high"]


def _iso_z(value: datetime) -> str:
    return value.isoformat() + ("" if value.tzinfo else "Z")


class ProcessRequest(BaseModel):
    url: Optional[str] = None
    file_path: Optional[str] = None
    platform: Platform
    caption: Optional[str] = None

    @model_validator(mode="after")
    def _needs_input(self) -> "ProcessRequest":
        if not self.url and not self.file_path:
            raise ValueError("Provide either 'url' or 'file_path'")
        return self


class LocationOut(BaseModel):
    description: Optional[str] = None
    borough: Optional[str] = None
    neighborhood: Optional[str] = None
    confidence: float
    needs_review: bool


class AgencyCandidate(BaseModel):
    name: str
    confidence: float = Field(ge=0, le=1)


class ObservationResponse(BaseModel):
    id: str
    source_id: str
    type: str
    topic: str
    summary: str
    location: LocationOut
    agency_candidates: list[AgencyCandidate]
    urgency: Optional[str] = None
    language: str
    confidence: float
    evidence: dict[str, Any]
    status: str
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
    final_agency: Optional[str] = None
    final_priority: Optional[str] = None
    created_at: datetime

    @field_serializer("created_at", "reviewed_at")
    def _ser_dt(self, value: Optional[datetime]) -> Optional[str]:
        return _iso_z(value) if value else None

    @classmethod
    def from_orm_obj(cls, obs: Observation) -> "ObservationResponse":
        return cls(
            id=obs.id,
            source_id=obs.source_id,
            type=obs.type,
            topic=obs.topic,
            summary=obs.summary,
            location=LocationOut(
                description=obs.location_description,
                borough=obs.borough,
                neighborhood=obs.neighborhood,
                confidence=obs.location_confidence,
                needs_review=obs.location_confidence < LOW_CONFIDENCE_THRESHOLD,
            ),
            agency_candidates=obs.agency_candidates or [],
            urgency=obs.urgency,
            language=obs.language,
            confidence=obs.confidence,
            evidence=obs.evidence or {},
            status=obs.status,
            reviewed_at=obs.reviewed_at,
            reviewer_notes=obs.reviewer_notes,
            final_agency=obs.final_agency,
            final_priority=obs.final_priority,
            created_at=obs.created_at,
        )


class ObservationList(BaseModel):
    total: int
    count: int
    observations: list[ObservationResponse]


class ObservationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[Status] = None
    final_agency: Optional[str] = None
    final_priority: Optional[Priority] = None
    reviewer_notes: Optional[str] = None
    type: Optional[ObservationType] = None
    topic: Optional[Topic] = None
    borough: Optional[Borough] = None
    urgency: Optional[Urgency] = None
    location_description: Optional[str] = None


class CivicSignalResponse(BaseModel):
    id: str
    title: str
    topic: str
    borough: str
    agency_candidates: list[AgencyCandidate]
    observation_ids: list[str]
    observation_count: int
    unique_source_count: Optional[int] = None
    trend: Optional[str] = None
    confidence: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def _ser_dt(self, value: datetime) -> str:
        return _iso_z(value)

    @classmethod
    def from_orm_obj(cls, sig: CivicSignal) -> "CivicSignalResponse":
        return cls.model_validate(sig)


class SignalList(BaseModel):
    total: int
    signals: list[CivicSignalResponse]


class AggregateResponse(BaseModel):
    message: str
    signals_created: int
    signals_updated: int
    groups_found: int


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


class ErrorResponse(BaseModel):
    error: str


class WorkflowRunRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=200)
    window_days: int = Field(5, ge=1, le=60)


class WorkflowRunResponse(BaseModel):
    counts: dict[str, int]
    results: list[dict[str, Any]]


class ServiceRequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complaint_type: Optional[str] = None
    descriptor: Optional[str] = None
    agency: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal["draft", "approved", "filed", "declined"]] = None
    sr_number: Optional[str] = None
