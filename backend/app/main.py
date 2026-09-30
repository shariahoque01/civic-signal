import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import schemas
from app.config import get_settings
from app.database import get_db, init_db
from app.models import CivicSignal, Observation, Source, _now
from app.services import gemini_service, video_service
from app.services.aggregator import aggregate_observations_simple, group_observations
from app.utils.constants import (
    APP_VERSION, CORS_ORIGINS, DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT,
)

logging.basicConfig(
    level=get_settings().log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("civic_signal")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    get_settings().upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Database initialised (env=%s)", get_settings().environment)
    yield


app = FastAPI(title="Civic Signal API", version=APP_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        {"error": "Invalid request", "details": jsonable_encoder(exc.errors(), custom_encoder={Exception: str})},
        status_code=422,
    )


@app.exception_handler(Exception)
async def unhandled_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error")
    return JSONResponse({"error": "Internal server error"}, status_code=500)


@app.get("/health", response_model=schemas.HealthResponse)
async def health() -> schemas.HealthResponse:
    return schemas.HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        version=APP_VERSION,
    )


@app.post("/api/process", response_model=schemas.ObservationResponse, status_code=201)
async def process(req: schemas.ProcessRequest, db: Session = Depends(get_db)) -> schemas.ObservationResponse:
    if req.url and not video_service.validate_url(req.url, req.platform):
        raise HTTPException(400, f"URL is not a valid {req.platform} link")
    if req.platform == "upload" and not req.file_path:
        raise HTTPException(400, "file_path is required when platform is 'upload'")
    if req.platform != "upload" and not req.url:
        raise HTTPException(400, f"url is required for platform '{req.platform}'")

    try:
        transcript, language, engagement = await video_service.get_video_content(
            req.url, req.platform, req.file_path
        )
        content = transcript if not req.caption else f"{transcript}\n\nUser caption: {req.caption}"
        extracted = await gemini_service.extract_observation(content, language)
        language = extracted["language"]
    except video_service.ExtractionError as exc:
        logger.error("Extraction failed: %s", exc)
        raise HTTPException(500, f"Extraction failed: {exc}")
    except gemini_service.GeminiError as exc:
        raise HTTPException(500, f"AI extraction failed: {exc}")

    source = Source(
        platform=req.platform, post_url=req.url, file_path=req.file_path,
        transcript=transcript, caption=req.caption, language=language, engagement=engagement,
    )
    obs = Observation(source=source, **extracted)
    db.add_all([source, obs])
    db.commit()
    logger.info("Created %s from %s", obs.id, source.id)
    return schemas.ObservationResponse.from_orm_obj(obs)


@app.get("/api/observations", response_model=schemas.ObservationList)
async def list_observations(
    status: Optional[schemas.Status] = None,
    borough: Optional[schemas.Borough] = None,
    topic: Optional[schemas.Topic] = None,
    type: Optional[schemas.ObservationType] = None,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> schemas.ObservationList:
    filters = [
        col == val
        for col, val in (
            (Observation.status, status), (Observation.borough, borough),
            (Observation.topic, topic), (Observation.type, type),
        )
        if val is not None
    ]
    total = db.scalar(select(func.count()).select_from(Observation).where(*filters)) or 0
    rows = db.scalars(
        select(Observation).where(*filters)
        .order_by(Observation.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return schemas.ObservationList(
        total=total, count=len(rows),
        observations=[schemas.ObservationResponse.from_orm_obj(o) for o in rows],
    )


def _get_observation(db: Session, observation_id: str) -> Observation:
    obs = db.get(Observation, observation_id)
    if obs is None:
        raise HTTPException(404, f"Observation {observation_id} not found")
    return obs


@app.get("/api/observations/{observation_id}", response_model=schemas.ObservationResponse)
async def get_observation(observation_id: str, db: Session = Depends(get_db)) -> schemas.ObservationResponse:
    return schemas.ObservationResponse.from_orm_obj(_get_observation(db, observation_id))


@app.patch("/api/observations/{observation_id}", response_model=schemas.ObservationResponse)
async def update_observation(
    observation_id: str, update: schemas.ObservationUpdate, db: Session = Depends(get_db)
) -> schemas.ObservationResponse:
    obs = _get_observation(db, observation_id)
    changes = update.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(obs, field, value)
    if changes:
        obs.reviewed_at = _now()
    db.commit()
    logger.info("Observation %s updated: %s", obs.id, sorted(changes))
    return schemas.ObservationResponse.from_orm_obj(obs)


@app.get("/api/signals", response_model=schemas.SignalList)
async def list_signals(db: Session = Depends(get_db)) -> schemas.SignalList:
    rows = db.scalars(select(CivicSignal).order_by(CivicSignal.observation_count.desc())).all()
    return schemas.SignalList(total=len(rows), signals=[schemas.CivicSignalResponse.from_orm_obj(s) for s in rows])


@app.post("/api/signals/aggregate", response_model=schemas.AggregateResponse)
async def aggregate(db: Session = Depends(get_db)) -> schemas.AggregateResponse:
    reviewed = list(db.scalars(select(Observation).where(Observation.status == "reviewed")).all())
    groups_found = len(group_observations(reviewed))
    created = updated = 0
    for data in aggregate_observations_simple(reviewed):
        existing = db.scalar(
            select(CivicSignal).where(CivicSignal.topic == data["topic"], CivicSignal.borough == data["borough"])
        )
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
            updated += 1
        else:
            db.add(CivicSignal(**data))
            created += 1
    db.commit()
    logger.info("Aggregation: %d groups, %d created, %d updated", groups_found, created, updated)
    return schemas.AggregateResponse(
        message="Aggregation complete", signals_created=created,
        signals_updated=updated, groups_found=groups_found,
    )
