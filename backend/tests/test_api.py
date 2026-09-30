import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.services import gemini_service, video_service

FAKE_RAW = {
    "type": "issue", "topic": "streetlights", "summary": "Light is out.",
    "location_description": "5th Ave & 42nd St", "borough": "Manhattan",
    "location_confidence": 0.9, "agency_candidates": [{"name": "NYC DOT", "confidence": 0.9}],
    "urgency": "medium", "language": "en", "confidence": 0.8, "evidence": {"quote": "The light is out"},
}


@pytest.fixture
def client(monkeypatch):
    Base.metadata.drop_all(engine)

    async def fake_content(url, platform, file_path=None):
        return "The light is out", "en", 5

    async def fake_extract(content, language):
        return gemini_service.normalize_observation(FAKE_RAW, language)

    async def fake_lang(content):
        return "en"

    monkeypatch.setattr(video_service, "get_video_content", fake_content)
    monkeypatch.setattr(gemini_service, "extract_observation", fake_extract)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


def _process(client):
    return client.post("/api/process", json={"url": "https://www.tiktok.com/@a/video/1", "platform": "tiktok"})


def test_health(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_process_and_fetch(client):
    r = _process(client)
    assert r.status_code == 201
    body = r.json()
    assert body["id"].startswith("obs_") and body["location"]["needs_review"] is False
    assert client.get(f"/api/observations/{body['id']}").status_code == 200
    assert client.get("/api/observations/nope").status_code == 404
    assert client.get("/api/observations?topic=streetlights").json()["total"] == 1
    assert client.get("/api/observations?topic=bogus").status_code == 422


def test_process_validation(client):
    r = client.post("/api/process", json={"url": "https://evil.com/tiktok.com", "platform": "tiktok"})
    assert r.status_code == 400 and "error" in r.json()
    assert client.post("/api/process", json={"platform": "tiktok"}).status_code == 422


def test_patch_and_aggregate(client):
    ids = [_process(client).json()["id"] for _ in range(2)]
    assert client.patch(f"/api/observations/{ids[0]}", json={"status": "bogus"}).status_code == 422
    for i in ids:
        r = client.patch(f"/api/observations/{i}", json={"status": "reviewed", "final_agency": "NYC DOT"})
        assert r.status_code == 200 and r.json()["reviewed_at"].endswith("Z")
    agg = client.post("/api/signals/aggregate").json()
    assert agg["signals_created"] == 1 and agg["groups_found"] == 1
    assert client.post("/api/signals/aggregate").json()["signals_updated"] == 1
    sigs = client.get("/api/signals").json()
    assert sigs["total"] == 1 and sigs["signals"][0]["observation_count"] == 2


def test_normalize_never_invents():
    out = gemini_service.normalize_observation({"topic": "aliens", "borough": "Atlantis", "summary": "x"})
    assert out["topic"] == "other" and out["borough"] is None
    assert out["location_confidence"] == 0.0 and out["agency_candidates"][0]["confidence"] <= 0.5


def test_upload_path_confined():
    with pytest.raises(video_service.ExtractionError):
        video_service.resolve_upload_path("/etc/passwd")
