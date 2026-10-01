"""Transcript insights: corpus-level views over all ingested videos (beyond one-video-one-ticket).

Everything here is computed with rules/statistics (no LLM required) and is labelled as heuristic.
"""
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.services.analysis import report

# One router (no nested routers) so main.py needs a single include line. All API paths live
# under PREFIX; the page itself is served at /insights.
PREFIX = "/api/insights"
router = APIRouter(tags=["insights"])
STATIC_DIR = Path(__file__).parent / "static"
Source = Literal["auto", "db", "corpus"]
SECTIONS = ("overview", "genres", "themes", "attention", "echoes", "voices", "quotes", "sentiment")


@router.get("/insights", include_in_schema=False)
async def insights_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "insights.html")


@router.get(PREFIX)
async def full_report(source: Source = "auto") -> dict:
    """Every section in one payload (what the /insights page uses)."""
    return report.build(source)


@router.get(f"{PREFIX}/records")
async def records(source: Source = "auto", limit: int = Query(200, ge=1, le=2000)) -> dict:
    recs, label = report.load(source)
    return {"source": label, "total": len(recs), "records": [r.public() for r in recs[:limit]]}


@router.get(f"{PREFIX}/quotes")
async def quotes(
    source: Source = "auto", theme: Optional[str] = None, genre: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Quote bank for policy memos, filterable by theme id or genre id."""
    data = report.build(source)
    rows = [q for q in data["quotes"]["items"]
            if (theme is None or theme in q["themes"]) and (genre is None or q["genre"] == genre)]
    return {"source": data["meta"]["source"], "total": len(rows), "items": rows[:limit]}


@router.get(f"{PREFIX}/sentiment")
async def sentiment(source: Source = "auto") -> dict:
    """What people are thinking: lexicon tone and emotional register (no LLM).

    Shape::

        {"meta": {...},
         "sentiment": {
           "overall": Agg, "asks": Agg | null,
           "by_theme": [{"theme", "label", **Agg}],          # sorted most negative first; themes with >= 2 videos
           "by_genre": [{"genre", "label", **Agg}],
           "over_time": [{"date": "YYYY-MM-DD", **Agg}],
           "registers": [{"id": "frustration|hope|humor|gratitude|worry", "label", "count", "share",
                          "by_genre": {genre: n}, "quotes": [Card + {"matched": [str]}]}],
           "most_negative": [Card + {"compound", "label", "pos_words", "neg_words"}],   # 5 each
           "most_positive": [...],
           "method": str, "caveat": str}}

        Agg  = {"n", "mean" (-1..1), "positive", "negative", "mixed", "neutral", "top_register"}
        Card = {"handle", "url", "posted_at", "views", "likes", "genre", "genre_label", "quote", "themes",
                "has_speech"}
    """
    data = report.build(source)
    return {"meta": data["meta"], "sentiment": data["sentiment"]}


@router.get(f"{PREFIX}/blind-spots")
async def blind_spots(source: Source = "auto") -> dict:
    """Office of Mass Engagement brief 1: what residents raise that official channels (311) miss.

    Shape::

        {"meta": {...},
         "blind_spots": {
           "summary": {"asks", "nyc_asks", "routable_to_311", "not_routable", "share_not_routable" (0..1),
                       "outside_nyc", "tried_official_channels", "quiet_but_serious"},
           "gaps": [{"id": "311_not_in_app|no_311_path|needs_viewing", "label", "count", "why_it_matters",
                     "items": [Card + {"place", "primary_theme", "sr_hint"}]}],      # up to 8 items each
           "unmet_themes": [{"theme", "label", "fit": "311|none", "route_hint", "resident_videos", "creators",
                             "asks", "views", "quotes": [Card]}],                   # up to 10
           "tried_official_channels": [Card + {"said": [str]}],    # "we've done the 311 calls..."
           "quiet_but_serious": [Card + {"severity", "severity_why", "views_percentile", "quadrant", ...}],
           "emerging_vocabulary": {"count", "top_terms": [str], "note"},
           "method": str}}
    """
    data = report.build(source)
    return {"meta": data["meta"], "blind_spots": data["blind_spots"]}


@router.get(f"{PREFIX}/engagement-plan")
async def engagement_plan(source: Source = "auto") -> dict:
    """Office of Mass Engagement brief 2: where to show up, what to answer publicly, who is speaking up.

    Shape::

        {"meta": {...},
         "engagement_plan": {
           "show_up": [{"borough", "place", "asks", "max_severity", "views", "themes": [theme_id],
                        "examples": [Card + {"severity"}]}],                       # NYC service asks by place
           "boroughs": {borough_or_"Unknown": n_asks},
           "events": [Card + {"event_words": [str], "dates_mentioned": [str]}],  # parades, celebrations...
           "respond_publicly": [                                                   # sorted by "priority" desc
               Card + {"kind": "unanswered_ask" | "amplify_fix" | "claim_check", "priority", "reason",
                       "claim_words"?: [str]}
             | {"kind": "narrative", "label", "videos", "creators", "views", "mean_tone", "priority",
                "reason", "examples": [{"handle", "url", "genre", "views", "posted_at", "quote"}]}],
           "communities": [{"community", "videos", "creators", "views", "mean_tone", "top_themes": [label],
                            "examples": [Card]}],     # videos *mentioning* a community; never labels people
           "languages": {code: n}, "non_english_speech": int,
           "method": str}}
    """
    data = report.build(source)
    return {"meta": data["meta"], "engagement_plan": data["engagement_plan"]}


@router.get(PREFIX + "/{section}")
async def section(section: str, source: Source = "auto") -> dict:
    """Any single section of the full report: {"meta": {...}, "<section>": {...}}."""
    if section not in SECTIONS:
        raise HTTPException(404, f"Unknown insights section '{section}'. Try one of: {', '.join(SECTIONS)}")
    data = report.build(source)
    return {"meta": data["meta"], section: data[section]}

