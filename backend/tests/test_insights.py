"""Insights analyses on a small, clearly synthetic fixture (handles and URLs are fake)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.analysis import annotate as ann
from app.services.analysis import records, report, sentiment
from app.services.analysis.records import Record, record_from_mapping, split_transcript

T0 = datetime(2026, 9, 26, 12, 0)


def rec(i: int, caption="", speech="", on_screen="", views=1000, hours=0, handle=None, **kw) -> Record:
    return Record(id=f"fx{i}", url=f"https://example.test/fixture/{i}", handle=handle or f"fixture_user_{i}",
                  posted_at=T0 + timedelta(hours=hours), caption=caption, speech=speech, on_screen=on_screen,
                  views=views, likes=views // 10, **kw)


ANNOUNCEMENT = ("Today the mayor announced the new jobs center at city hall. The center helps New Yorkers find "
                "city jobs, walk in Monday through Thursday, the commissioner said.")
FIXTURE = [
    rec(1, caption="Mamdani fix this pothole on Lexington please", hashtags=["mamdanifixthis"],
        speech="Yo Mamdani I need you to fix this pothole, someone's gonna get hurt", views=700, hours=1),
    rec(2, caption="Whole sidewalk flooded in Far Rockaway @Mayor Mamdani", mentions=["nycmayor"], views=900, hours=2),
    rec(3, caption="Mamdani please fix this elevator", location_tag="UH-Downtown, Houston, TX 77002, USA",
        speech="this elevator has been broken for three months, we need your help", views=4000, hours=3),
    rec(4, caption="Mamdani fix my life please 😭", views=300, hours=4),
    rec(5, caption="mamdani fix this", views=200, hours=5),
    rec(6, caption="Mayor Mamdani jobs center", speech=ANNOUNCEMENT, handle="nbcnewyork", views=90000, hours=6),
    rec(7, caption="mayor jobs center launch", speech=ANNOUNCEMENT + " Truly an amazing day.", handle="ny1",
        views=50000, hours=7),
    rec(8, caption="Mamdani jobs center", speech=ANNOUNCEMENT + " Go apply!", views=20000, hours=8),
    rec(9, caption="I love our mayor Mamdani ❤️ he is the best", views=60000, hours=9),
    rec(10, caption="Fix this slime disaster #fixthis", views=100, hours=10),
    rec(11, caption="He fixed it! Mamdani got the pothole fixed in two days", views=150000, hours=30),
    rec(12, caption="Mamdani, the concrete factory has to go @Mayor", mentions=["nycmayor"],
        location_tag="Community Garden, 414 E 163rd St, Bronx, NY 10451, USA",
        speech="We've done the 3 1 1 calls, we've done the community board, nothing is getting done. "
               "The kids here can't breathe, enough is enough. This factory pollution has been here for years.",
        views=500, hours=12),
]


@pytest.fixture(scope="module")
def built() -> dict:
    return report.build_from_records(FIXTURE, "fixture")


def test_split_transcript_and_tolerant_mapping():
    blob = "Caption: hi there\nLocation tag on post: Bronx, NY\nOn-screen text: FIX IT\nSpoken (TikTok captions): hello"
    parts = split_transcript(blob)
    assert parts == {"caption": "hi there", "location_tag": "Bronx, NY", "on_screen": "FIX IT", "speech": "hello"}
    r = record_from_mapping({"id": "s1", "transcript": blob, "view_count": "12", "hashtags": '["#NYC"]',
                             "brand_new_column": 1, "engagement": None})
    assert (r.caption, r.speech, r.views, r.likes, r.hashtags) == ("hi there", "hello", 12, 0, ["nyc"])


def test_genres():
    g = {r.id: ann.annotate(r).genre for r in FIXTURE}
    assert g["fx1"] == "service_ask"
    assert g["fx2"] == "service_ask"            # tagging the mayor on a problem counts as the ask
    assert g["fx3"] == "service_ask_elsewhere"  # Houston location tag
    assert g["fx4"] == "personal_ask"
    assert g["fx5"] == "visual_ask"
    assert g["fx6"] == "news_official"
    assert g["fx10"] == "off_topic"
    assert g["fx11"] == "response"
    assert g["fx12"] == "service_ask"


def test_severity_and_tried_channels(built):
    att = built["attention"]
    top = att["items"][0]
    assert top["handle"] == "fixture_user_12" and top["severity"] >= 5
    assert "tried_channels" in top["severity_why"]
    assert any(i["handle"] == "fixture_user_12" for i in att["quiet_but_serious"])
    assert ann.duration_days("broken for three months") == 90


def test_fit_gap_buckets(built):
    buckets = {b["id"]: [i["handle"] for i in b["items"]] for b in built["themes"]["fit_gap"]}
    assert "fixture_user_1" in buckets["drafts_cleanly"]
    assert "fixture_user_12" in buckets["311_not_in_app"]   # air quality: real 311 type, not drafted by the app
    assert "fixture_user_3" in buckets["outside_nyc"]
    assert "fixture_user_4" in buckets["no_311_path"]
    assert "fixture_user_5" in buckets["needs_viewing"]


def test_waves_and_closures(built):
    jobs = [w for w in built["echoes"]["waves"] if w["theme"] == "jobs_services"]
    assert jobs and jobs[0]["creators"] == 3 and jobs[0]["news_or_official"] >= 2
    closure = built["echoes"]["closures"][0]
    assert closure["handle"] == "fixture_user_11"
    assert closure["candidate_asks"][0]["handle"] == "fixture_user_1"  # earlier pothole ask, same theme
    dups = built["echoes"]["duplicates"]
    assert dups and dups[0]["creators"] >= 2  # the three near-identical announcement relays


def test_sentiment_lexicon():
    assert sentiment.tone("I love this, it is amazing ❤️").label == "positive"
    assert sentiment.tone("this is terrible and dangerous, I hate it").label == "negative"
    assert sentiment.tone("this is not good").compound < 0  # negation flips
    assert "frustration" in sentiment.tone("enough is enough, I'm sick and tired").registers


def test_report_sections_and_ome(built):
    for key in ("meta", "overview", "genres", "themes", "attention", "echoes", "voices", "quotes", "sentiment",
                "blind_spots", "engagement_plan"):
        assert key in built
    assert built["meta"]["records"] == len(FIXTURE)
    assert built["overview"]["headlines"]
    s = built["blind_spots"]["summary"]
    assert s["tried_official_channels"] == 1 and s["routable_to_311"] >= 1
    plan = built["engagement_plan"]
    assert any(p["borough"] == "Bronx" for p in plan["show_up"])
    kinds = {q["kind"] for q in plan["respond_publicly"]}
    assert "amplify_fix" in kinds
    assert {r["id"] for r in built["sentiment"]["registers"]} >= {"frustration", "hope", "humor"}


def test_empty_corpus_does_not_crash():
    out = report.build_from_records([], "empty")
    assert out["meta"]["records"] == 0 and out["overview"]["headlines"] == []


def test_endpoints(monkeypatch):
    monkeypatch.setattr(records, "load_records", lambda prefer="auto": (FIXTURE, "fixture"))
    monkeypatch.setattr(report, "load_records", lambda prefer="auto": (FIXTURE, "fixture"))
    report._cache.clear()
    with TestClient(app) as c:
        assert c.get("/insights").status_code == 200
        full = c.get("/api/insights").json()
        assert full["meta"]["source"] == "fixture"
        for path, key in (("sentiment", "sentiment"), ("blind-spots", "blind_spots"),
                          ("engagement-plan", "engagement_plan"), ("echoes", "echoes")):
            r = c.get(f"/api/insights/{path}")
            assert r.status_code == 200 and key in r.json(), path
        q = c.get("/api/insights/quotes", params={"genre": "service_ask"}).json()
        assert q["total"] >= 1 and all(i["genre"] == "service_ask" for i in q["items"])
        assert c.get("/api/insights/nope").status_code == 404
    report._cache.clear()
