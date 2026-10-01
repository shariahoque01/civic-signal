"""Briefs for the NYC Office of Mass Engagement: what official channels miss, and where/what/who to engage.

Everything is derived from public posts with rules; each item says why it was surfaced.
"""
import math
import re
import statistics
from collections import Counter, defaultdict
from typing import Optional

from app.services.analysis import lexicons as L
from app.services.analysis.annotate import ASK_GENRES, GENRES, SERVICE_GENRES, Annotation
from app.services.analysis.sentiment import Tone
from app.services.analysis.textutil import find_terms

BOROUGH_TAGS = {"brooklyn": "Brooklyn", "kings": "Brooklyn", "bronx": "Bronx", "queens": "Queens",
                "staten island": "Staten Island", "richmond": "Staten Island", "manhattan": "Manhattan"}
NEIGHBORHOOD_BOROUGH = {"far rockaway": "Queens", "farrockaway": "Queens", "rockaway": "Queens", "astoria": "Queens",
                        "bushwick": "Brooklyn", "flatbush": "Brooklyn", "kings highway": "Brooklyn",
                        "kingshighway": "Brooklyn", "bed-stuy": "Brooklyn", "williamsburg": "Brooklyn",
                        "harlem": "Manhattan", "lexington": "Manhattan", "penn station": "Manhattan",
                        "melrose": "Bronx", "jamaica": "Queens", "flushing": "Queens"}
CLAIM_TERMS = ("lied", "liar", "promised", "(no)", "not true", "fake", "didn't", "hasn't", "never did", "is it true",
               "the truth about", "doesn't deserve", "more expensive", "botched", "controlled opposition",
               "compromised", "can't arrest", "won't tell you")
COMMUNITY_TERMS = {
    "Nigerian": ("nigeria", "nigerian", "nigerians", "lagos"), "Jewish": ("jewish", "jews", "shul", "shuls"),
    "Palestinian / Arab": ("palestinian", "palestine", "arab"), "Muslim": ("muslim", "muslims", "mosque"),
    "Black New Yorkers": ("black men", "black women", "blackpeople", "black people", "black community"),
    "South Asian / brown": ("brown man", "brown men", "desi", "bangladeshi", "indian", "pakistani"),
    "Latino / Hispanic": ("latino", "latina", "latinx", "hispanic", "dominican", "puerto rican", "mexican"),
    "Caribbean": ("jamaican", "haitian", "trinidad", "guyanese", "caribbean"),
    "LGBTQ+ / trans": ("trans", "transgender", "transwoman", "lgbtq", "queer", "lgbtqia"),
    "Immigrants": ("immigrant", "immigrants", "migrants", "migrant"),
    "NYCHA residents": ("nycha", "public housing", "tenants"),
    "Families & students (mentions kids/school)": ("students", "kids", "youth", "teens", "school"),
    "Workers": ("delivery workers", "workers", "union", "vendors"),
}
EVENT_TERMS = ("parade", "festival", "celebration", "birthday", "independence day", "rally", "town hall", "block party",
               "march", "vigil", "partiful")
DATE_RE = re.compile(r"\b(?:(?:first|second|third|last)\s+\w+day\s+of\s+\w+|this\s+(?:saturday|sunday|weekend|friday)|"
                     r"\d{1,2}/\d{1,2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+\d{1,2})\b", re.I)


def _card(a: Annotation, **extra) -> dict:
    r = a.record
    return {"handle": r.handle, "url": r.url, "posted_at": r.posted_at.isoformat() + "Z" if r.posted_at else None,
            "views": r.views, "genre": a.genre, "genre_label": GENRES[a.genre]["label"], "quote": a.quote,
            "themes": a.themes, **extra}


def area(a: Annotation) -> tuple[Optional[str], Optional[str]]:
    """(borough, neighborhood/place) from the location tag first, then named places in the text."""
    tag = (a.record.location_tag or "")
    low = tag.lower()
    borough = next((b for k, b in BOROUGH_TAGS.items() if re.search(rf"\b{k}\b", low)), None)
    place = tag.split(",")[0].strip() if tag and borough else None
    if borough is None:
        try:
            from app.services.heuristics import _find_area  # shared NYC neighborhood list

            hood, b = _find_area(a.record.text + " " + " ".join("#" + h for h in a.record.hashtags))
        except Exception:  # noqa: BLE001
            hood, b = None, None
        if b:
            return b, hood
        hint = (a.place_hint or "").lower()
        if hint in NEIGHBORHOOD_BOROUGH:
            return NEIGHBORHOOD_BOROUGH[hint], a.place_hint.title()
    return borough, place


# --- 1. Blind spots --------------------------------------------------------------------------------------
def blind_spots(anns: list[Annotation], fit_gap: list[dict], attention: dict, unthemed: dict) -> dict:
    asks = [a for a in anns if a.genre in ASK_GENRES]
    nyc_asks = [a for a in asks if a.in_nyc is not False and a.genre != "service_ask_elsewhere"]
    buckets = {b["id"]: b for b in fit_gap}
    routable = buckets.get("drafts_cleanly", {}).get("count", 0)
    why = {
        "311_not_in_app": "311 has a form for these, but the intake pipeline doesn't draft them, so they're "
                          "dropped unless someone reads the video.",
        "no_311_path": "There's no 311 form at all: schools, transit fares, personal pleas. Only an engagement "
                       "team can answer these.",
        "needs_viewing": "The words don't say what's wrong; the problem is in the picture. Text-only triage "
                         "misses all of these.",
    }
    gaps = [{"id": k, "label": buckets[k]["label"], "count": buckets[k]["count"], "why_it_matters": why[k],
             "items": buckets[k]["items"][:8]} for k in why if k in buckets]

    # Themes residents raise (not news) that have no 311 path, ranked by resident voices.
    unmet = []
    for tid, t in L.THEMES.items():
        if t["fit"] == "app":
            continue
        group = [a for a in anns if tid in a.themes and a.genre not in ("news_official", "off_topic")]
        if len(group) < 2:
            continue
        group.sort(key=lambda a: (-(a.genre in ASK_GENRES), -a.record.views))
        unmet.append({"theme": tid, "label": t["label"], "fit": t["fit"], "route_hint": t["sr_hint"],
                      "resident_videos": len(group), "creators": len({a.record.handle for a in group}),
                      "asks": sum(1 for a in group if a.genre in ASK_GENRES),
                      "views": sum(a.record.views for a in group), "quotes": [_card(a) for a in group[:3]]})
    unmet.sort(key=lambda u: (-u["asks"], -u["resident_videos"]))
    not_routable = len(nyc_asks) - routable
    return {
        "summary": {
            "asks": len(asks), "nyc_asks": len(nyc_asks), "routable_to_311": routable,
            "not_routable": max(not_routable, 0),
            "share_not_routable": round(max(not_routable, 0) / len(nyc_asks), 3) if nyc_asks else 0,
            "outside_nyc": buckets.get("outside_nyc", {}).get("count", 0),
            "tried_official_channels": len(attention["tried_official_channels"]),
            "quiet_but_serious": len(attention["quiet_but_serious"]),
        },
        "gaps": gaps,
        "unmet_themes": unmet[:10],
        "tried_official_channels": attention["tried_official_channels"],
        "quiet_but_serious": attention["quiet_but_serious"][:10],
        "emerging_vocabulary": unthemed,
        "method": "Asks are bucketed by whether a 311 form exists for their main theme; themes are keyword lexicons; "
                  "'tried official channels' means the speaker says they already used 311 or the community board.",
    }


# --- 2. Engagement plan ----------------------------------------------------------------------------------
def engagement_plan(anns: list[Annotation], tones: dict[str, Tone], waves: list[dict], closures: list[dict]) -> dict:
    views_all = sorted(a.record.views for a in anns) or [0]
    p75 = views_all[int(0.75 * (len(views_all) - 1))]
    median = int(statistics.median(views_all))

    # Where to show up: places with resident asks, ranked by asks then severity.
    places: dict[tuple, list[Annotation]] = defaultdict(list)
    boroughs: Counter = Counter()
    for a in anns:
        if a.genre not in SERVICE_GENRES or a.in_nyc is False:
            continue
        b, p = area(a)
        boroughs[b or "Unknown"] += 1
        places[(b or "Unknown borough", p or "place not stated")].append(a)
    show_up = sorted(
        ({"borough": b, "place": p, "asks": len(g), "max_severity": max(x.severity for x in g),
          "views": sum(x.record.views for x in g),
          "themes": [t for t, _ in Counter(t for x in g for t in x.themes[:1]).most_common(3)],
          "examples": [_card(x, severity=x.severity) for x in sorted(g, key=lambda x: -x.severity)[:3]]}
         for (b, p), g in places.items()),
        key=lambda s: (s["place"] == "place not stated", -s["asks"], -s["max_severity"]),
    )
    events = []
    for a in anns:
        hits = find_terms(a.record.text, EVENT_TERMS)
        if hits and a.genre not in ("news_official", "off_topic"):
            dates = DATE_RE.findall(a.record.text)
            events.append(_card(a, event_words=hits, dates_mentioned=dates[:3]))
    events.sort(key=lambda e: -e["views"])

    # What to respond to publicly.
    linked = {c["url"] for cl in closures for c in cl.get("candidate_asks", [])}
    queue = []
    for a in anns:
        r, t = a.record, tones.get(a.record.id)
        if a.genre in SERVICE_GENRES and a.in_nyc is not False and r.url not in linked and r.views >= median:
            queue.append(_card(a, kind="unanswered_ask", priority=round(math.log10(r.views + 10) + a.severity, 2),
                               reason=f"NYC ask with {r.views:,} views and no follow-up found. Reply publicly and route it."))
        elif a.genre == "response" and r.views >= median:
            queue.append(_card(a, kind="amplify_fix", priority=round(math.log10(r.views + 10), 2),
                               reason="Fix story. Credit the crew and the resident who reported it."))
        elif a.genre in ("commentary", "news_official") and r.views >= p75:
            claims = find_terms(r.text, CLAIM_TERMS)
            if claims and t and t.label in ("negative", "mixed"):
                queue.append(_card(a, kind="claim_check", priority=round(math.log10(r.views + 10) - 1, 2),
                                   claim_words=claims[:4],
                                   reason="Widely seen critical claim about city action. Check the facts before "
                                          "deciding whether to explain publicly."))
    for w in waves:
        tone_vals = [tones[m_id].compound for m_id in w.get("member_ids", []) if m_id in tones]
        mean = sum(tone_vals) / len(tone_vals) if tone_vals else 0.0
        if w["residents_and_others"] >= max(2, w["news_or_official"]):
            queue.append({"kind": "narrative", "label": w["label"], "videos": w["videos"], "creators": w["creators"],
                          "views": w["views"], "mean_tone": round(mean, 2),
                          "priority": round(math.log10(w["views"] + 10) + w["creators"] / 3 - (mean * 2), 2),
                          "reason": f"{w['creators']} creators, mostly residents, are talking about this "
                                    f"(mean tone {mean:+.2f}). A public conversation the office could join.",
                          "examples": w["members"][:3]})
    queue.sort(key=lambda q: -q["priority"])
    seen_labels: set = set()
    queue = [q for q in queue if q["kind"] != "narrative" or not (q["label"] in seen_labels or seen_labels.add(q["label"]))]

    # Who is speaking up: communities mentioned, languages, self-described speakers.
    comm = []
    for label, terms in COMMUNITY_TERMS.items():
        group = [a for a in anns if find_terms(a.record.text + " " + " ".join("#" + h for h in a.record.hashtags), terms)]
        if group:
            tl = [tones[a.record.id].compound for a in group if a.record.id in tones]
            comm.append({"community": label, "videos": len(group), "creators": len({a.record.handle for a in group}),
                         "views": sum(a.record.views for a in group),
                         "mean_tone": round(sum(tl) / len(tl), 2) if tl else 0.0,
                         "top_themes": [L.THEMES[t]["label"] for t, _ in
                                        Counter(t for a in group for t in a.themes[:2]).most_common(3)],
                         "examples": [_card(a) for a in sorted(group, key=lambda a: -a.record.views)[:2]]})
    comm.sort(key=lambda c: -c["videos"])
    langs = Counter((a.record.language or "unknown") for a in anns if a.record.has_speech)
    return {
        "show_up": show_up[:12],
        "boroughs": dict(boroughs.most_common()),
        "events": events[:8],
        "respond_publicly": queue[:20],
        "communities": comm,
        "languages": dict(langs.most_common()),
        "non_english_speech": sum(v for k, v in langs.items() if k not in ("en", "unknown")),
        "method": "Places come from post location tags, then neighborhood names in the text. Response priority "
                  "is log10(views) plus severity (asks), or reach plus creator count minus tone (narratives). "
                  "Community rows count videos that mention a community; they never label any person.",
    }
