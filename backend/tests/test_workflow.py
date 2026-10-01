import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.services import geo, heuristics, tiktok_service, workflow
from app.services.routing import community_board_name
from app.services.video_service import PostMetadata

RECENT_ID = str(int(datetime.now().timestamp()) << 32)
URL = f"https://www.tiktok.com/@resident/video/{RECENT_ID}"


@pytest.fixture
def client(monkeypatch):
    Base.metadata.drop_all(engine)

    async def fake_post(url):
        return tiktok_service.TikTokPost(
            meta=PostMetadata(creator_handle="resident", posted_at=datetime.utcnow(), view_count=900,
                              caption="@zohrankmamdani fix this #mamdanifixthis @nycdot",
                              mentions=["zohrankmamdani", "nycdot"], hashtags=["mamdanifixthis"]),
            speech="There's a huge pothole at Church Ave and Flatbush Ave in Brooklyn. It's dangerous.",
        )

    async def fake_locate(location, neighborhood, borough):
        return geo.GeoResult(label="Church Avenue & Flatbush Avenue", latitude=40.65, longitude=-73.96,
                             community_district=314, council_district=40, borough="Brooklyn", precision="address")

    monkeypatch.setattr(tiktok_service, "fetch_post", fake_post)
    monkeypatch.setattr(geo, "locate", fake_locate)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


def test_workflow_end_to_end(client):
    r = client.post("/api/workflow/run", json={"urls": [URL, URL]}).json()
    assert r["counts"] == {"processed": 1}
    case = client.get("/api/cases").json()["cases"][0]
    sr = case["service_request"]
    assert sr["complaint_type"] == "Street Condition" and sr["agency"] == "NYC DOT"
    assert sr["community_board"] == "Brooklyn Community Board 14"
    kinds = {x["kind"] for x in sr["routing"]}
    assert {"agency", "community_board", "council", "borough_president", "tagged"} <= kinds
    assert "pothole" in sr["description"] and URL in sr["description"]
    assert client.post("/api/workflow/run", json={"urls": [URL]}).json()["counts"] == {"skipped": 1}
    updated = client.patch(f"/api/service-requests/{sr['id']}", json={"status": "filed", "sr_number": "311-123"}).json()
    assert updated["service_request"]["status"] == "filed"
    assert client.patch(f"/api/service-requests/{sr['id']}", json={"status": "sent"}).status_code == 422


def test_old_tiktok_skipped_without_fetch(client):
    old_id = str(int((datetime.now() - timedelta(days=30)).timestamp()) << 32)
    r = client.post("/api/workflow/run", json={"urls": [f"https://www.tiktok.com/@a/video/{old_id}"]}).json()
    assert r["results"][0]["status"] == "skipped" and "window" in r["results"][0]["reason"]


def test_posted_at_from_id():
    assert tiktok_service.posted_at_from_id("https://www.tiktok.com/@x/video/7691055477668531478").year == 2026


def test_matches_query():
    meta = PostMetadata(caption="love this city", hashtags=["nyc"])
    assert workflow.matches_query(meta, "") == (False, False)
    assert workflow.matches_query(PostMetadata(hashtags=["mamdanifixthis"]), "") == (True, True)
    assert workflow.matches_query(PostMetadata(caption="Mamdani please fix this"), "") == (True, True)


def test_outside_nyc():
    assert workflow.outside_nyc("I'm in Beverly Hills, fix this pole") == "beverly hills"
    assert workflow.outside_nyc("Hay basura en la calle en el Bronx") is None


def test_heuristics_location_and_topic():
    out = heuristics.extract("Spoken (TikTok captions): The streetlight on 350 5th Ave has been out for weeks")
    assert out["topic"] == "streetlights" and out["location_description"] == "350 5th Ave"
    assert out["confidence"] < 0.5
    out = heuristics.extract("Caption: rats everywhere in Bed-Stuy #mamdanifixthis")
    assert out["topic"] == "rats" and out["neighborhood"] == "Bed-Stuy" and out["borough"] == "Brooklyn"


def test_community_board_names():
    assert community_board_name(314) == "Brooklyn Community Board 14"
    assert "no community board" in community_board_name(355)
    assert community_board_name(None) is None


def test_normalize_street_text():
    assert geo.normalize_street_text("Church Ave and Flatbush Ave") == "Church Avenue & Flatbush Avenue"


def _fake_unrelated(monkeypatch, caption="Mamdani's speech today was great #mamdani #nyc", hashtags=("mamdani", "nyc")):
    async def fake_post(url):
        return tiktok_service.TikTokPost(
            meta=PostMetadata(creator_handle="commentator", posted_at=tiktok_service.posted_at_from_id(url),
                              caption=caption, hashtags=list(hashtags)),
            speech="He talked about rent and buses.", speech_language="en", comment_count=4, share_count=2,
        )
    monkeypatch.setattr(tiktok_service, "fetch_post", fake_post)


def test_non_fix_video_is_stored_not_drafted(client, monkeypatch):
    from app.database import SessionLocal
    from app.models import Source

    _fake_unrelated(monkeypatch)
    r = client.post("/api/workflow/run", json={"urls": [URL]}).json()
    assert r["counts"] == {"stored": 1} and r["results"][0]["relevance"] == "mayor_related"
    assert client.get("/api/cases").json()["total"] == 0  # dashboard only shows fix requests
    with SessionLocal() as db:
        src = db.query(Source).one()
        assert src.relevance == "mayor_related" and src.has_speech and src.speech_text.startswith("He talked")
        assert src.comment_count == 4 and src.share_count == 2 and src.speech_language == "en"
        assert not src.observations


async def test_corpus_ingest_keeps_old_posts_and_merges_discovered_via(client, monkeypatch):
    from app.database import SessionLocal

    _fake_unrelated(monkeypatch, caption="bagels", hashtags=("food",))
    old_id = str(int((datetime.now() - timedelta(days=30)).timestamp()) << 32)
    url = f"https://www.tiktok.com/@a/video/{old_id}"
    with SessionLocal() as db:
        r = await workflow.process_url(db, url, None, discovered_via=["#mamdani"])
        assert r["status"] == "stored" and r["relevance"] == "unrelated"
        r = await workflow.process_url(db, url, None, discovered_via=["#heymamdani"])
        assert r["status"] == "skipped"
        src = db.scalar(workflow.select(workflow.Source))
        assert src.discovered_via == ["#mamdani", "#heymamdani"] and src.posted_at < datetime.now() - timedelta(days=29)


def test_relevance_labels():
    assert workflow.relevance(PostMetadata(hashtags=["fixthismamdani"]), "") == "fix_request"
    assert workflow.relevance(PostMetadata(caption="Zohran won the debate"), "") == "mayor_related"
    assert workflow.relevance(PostMetadata(caption="best pizza in nyc", hashtags=["nyc"]), "") == "unrelated"


def test_snowball_prefers_relevant_cooccurring_tags():
    from scripts.discover_tiktok import next_tags

    found = {str(i): {"caption": "mamdani fix this", "hashtags": ["mamdani", "fyp", "nycpotholes", "zohranfixit"]}
             for i in range(4)}
    found["x"] = {"caption": "cats", "hashtags": ["cats"] * 1}
    assert next_tags(found, {"mamdani"}, 5) == ["zohranfixit"]  # only Mamdani/mayor-hinted tags by default
    assert next_tags(found, {"mamdani"}, 5, broad=True) == ["zohranfixit", "nycpotholes"]


def test_outside_nyc_relevance():
    fix = PostMetadata(caption="I have no other choice but this")
    tbilisi = "On-screen text: Mamdani, please fix this. Everyday problem at the entrance to Didi Dighomi in Tbilisi."
    assert workflow.relevance(fix, tbilisi) == "outside_nyc"
    # location tag elsewhere, only #nyc as NYC evidence
    assert workflow.relevance(PostMetadata(caption="mamdani fix this #nyc", hashtags=["nyc"]), "",
                              "Saint James, Phelps County, Missouri, United States") == "outside_nyc"
    # names another city but is clearly about New York
    assert workflow.relevance(fix, "Spoken: Mamdani fix this. I'm in New York, London would never") == "fix_request"
    assert workflow.relevance(fix, "Mamdani fix this pothole", "Kings Highway, Brooklyn, NY 11234") == "fix_request"
    # NYC names that collide with other places stay in NYC
    assert not workflow.is_outside_nyc("Mamdani fix this on Houston St") and not workflow.is_outside_nyc("long island city")
    assert workflow.relevance(PostMetadata(), "Spoken (TikTok captions): Mom Donnie, fix this pothole now") == "fix_request"
