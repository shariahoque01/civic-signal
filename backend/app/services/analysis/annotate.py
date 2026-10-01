"""Per-video heuristic annotation: genre, place, themes, severity cues, self-described speaker cues.

All rule-based and explainable: each annotation carries the matched terms as `why`.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.analysis import lexicons as L
from app.services.analysis.records import Record
from app.services.analysis.textutil import best_sentence, find_terms

GENRES: dict[str, dict] = {
    "service_ask": {"label": "Service ask (NYC)", "desc": "A place-bound problem plus an ask, in NYC."},
    "service_ask_elsewhere": {"label": "Service ask (outside NYC)", "desc": "The trend's format copied for a "
                              "problem in another city or country. Not NYC's to fix."},
    "response": {"label": "Fixed / responded", "desc": "Says a problem got fixed or the mayor's team responded. "
                 "These close the loop on earlier asks."},
    "visual_ask": {"label": "Ask, problem shown only on video", "desc": "\"Fix this\" with no words describing "
                   "the problem. A human has to watch it."},
    "personal_ask": {"label": "Playful / personal ask", "desc": "The \"fix this\" format applied to a non-city "
                     "thing (a day off school, one's love life, an ice-cream flavor)."},
    "news_official": {"label": "News & official", "desc": "News outlets and relays of city announcements."},
    "commentary": {"label": "Political commentary", "desc": "Opinion about the mayor, national or foreign politics."},
    "fandom": {"label": "Praise & fandom", "desc": "Appreciation, admiration, celebrations."},
    "meme": {"label": "Meme & entertainment", "desc": "Edits, skits, late-night clips, jokes."},
    "off_topic": {"label": "Off-topic (hashtag overlap)", "desc": "Uses #fixthis-type tags but never mentions the mayor."},
}
ASK_GENRES = ("service_ask", "service_ask_elsewhere", "visual_ask", "personal_ask")
SERVICE_GENRES = ("service_ask", "service_ask_elsewhere", "visual_ask")
MAYOR_HANDLES = {"nycmayor", "zohran_k_mamdani", "zohrankmamdani"}
HEAD_SPEECH_CHARS = 320  # a service ask states the problem up front; long speeches drift
VISUAL_ASK_RE = re.compile(r"\b(fix|stop|help with)\s+(this|it)\b|what (the \w+ )?is this", re.I)
_WORD_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


@dataclass
class Annotation:
    record: Record
    genre: str
    genre_why: list[str]
    genre_confidence: str
    in_nyc: Optional[bool]
    place_why: list[str]
    place_hint: Optional[str]
    themes: list[str]
    theme_hits: dict[str, list[str]]
    severity: float
    severity_why: dict[str, list[str]]
    duration_days: Optional[int]
    cues: dict[str, list[str]]
    quote: Optional[str]
    closure: list[str] = field(default_factory=list)

    @property
    def is_ask(self) -> bool:
        return self.genre in ASK_GENRES


def _head(r: Record) -> str:
    return "\n".join([r.caption, r.on_screen, r.speech[:HEAD_SPEECH_CHARS]])


def _mentions_mayor(r: Record) -> bool:
    blob = " ".join([r.text, " ".join(r.hashtags), " ".join(r.mentions)]).lower()
    return any(t in blob for t in L.MAYOR_TERMS)


def place(r: Record) -> tuple[Optional[bool], list[str], Optional[str]]:
    """(in_nyc, why, hint). Location tag is the strongest signal; then place names in text/hashtags."""
    tag = (r.location_tag or "").lower()
    if tag:
        nyc = find_terms(tag, L.NYC_PLACE_TERMS)
        if nyc:
            return True, [f"location tag: {r.location_tag}"], r.location_tag
        return False, [f"location tag: {r.location_tag}"], r.location_tag
    blob = _head(r) + " " + " ".join("#" + h for h in r.hashtags)
    non = find_terms(blob, L.NON_NYC_PLACE_TERMS)
    if non:
        return False, [f"mentions {t}" for t in non], non[0]
    nyc = [t for t in find_terms(blob, L.NYC_PLACE_TERMS) if t not in ("nyc", "new york")]
    if nyc:
        return True, [f"mentions {t}" for t in nyc], nyc[0]
    return None, ["no place cue"], None


def classify_genre(r: Record) -> tuple[str, list[str], str]:
    handle = (r.handle or "").lower()
    text = r.text.lower() + " " + " ".join("#" + h for h in r.hashtags)
    head = _head(r)
    if not _mentions_mayor(r):
        return "off_topic", ["no mention of the mayor"], "high"
    closure = find_terms(r.caption + "\n" + r.on_screen + "\n" + r.speech[:HEAD_SPEECH_CHARS], L.CLOSURE_TERMS)
    if closure:
        return "response", [f"closure words: {', '.join(closure[:3])}"], "medium"
    problems = find_terms(head, L.PROBLEM_TERMS + ("problem",))
    asks = find_terms(head, L.ASK_TERMS)
    tagged = set(r.mentions) & MAYOR_HANDLES or re.search(r"@mayor|@zohran", r.caption, re.I)
    short_post = len(r.caption) + len(r.on_screen) < 250  # long captions are relays/explainers, not reports
    if tagged and short_post and find_terms(r.caption + "\n" + r.on_screen, L.PROBLEM_TERMS):
        asks.append("tags the mayor")  # tagging the mayor on a problem is itself the ask
    personal = find_terms(text, L.PERSONAL_ASK_TERMS)
    scores: dict[str, float] = {
        "news_official": (3.0 if handle in L.NEWS_HANDLES else 0) + 0.5 * len(find_terms(text, L.NEWS_TERMS)),
        "commentary": 0.7 * len(find_terms(text, L.COMMENTARY_TERMS)),
        "fandom": 0.8 * len(find_terms(text, L.FANDOM_TERMS)),
        "meme": 0.8 * len(find_terms(text, L.MEME_TERMS)) + (3.0 if handle in L.ENTERTAINMENT_HANDLES else 0),
        "service_ask": (2.0 + 1.2 * len(problems) + 0.8 * len(asks)) if problems and asks else 0.0,
        "personal_ask": (2.5 + len(personal)) if personal and (asks or "do something" in text) else 0.0,
    }
    words = len(r.text.split())
    if asks and not problems and not personal and VISUAL_ASK_RE.search(head) and words < 60:
        scores["visual_ask"] = 3.0
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (genre, top), (_, second) = ranked[0], ranked[1]
    if top <= 0:
        return "fandom" if words < 40 else "commentary", ["no strong cue (default)"], "low"
    why = {
        "service_ask": [f"problem: {', '.join(problems[:4])}", f"ask: {', '.join(asks[:4])}"],
        "personal_ask": [f"personal ask: {', '.join(personal[:3])}"],
        "visual_ask": ["'fix/stop this' with no problem words; short text"],
        "news_official": ([f"news account @{handle}"] if handle in L.NEWS_HANDLES else [])
        + [f"news words: {', '.join(find_terms(text, L.NEWS_TERMS)[:4])}"],
        "commentary": [f"political words: {', '.join(find_terms(text, L.COMMENTARY_TERMS)[:5])}"],
        "fandom": [f"praise words: {', '.join(find_terms(text, L.FANDOM_TERMS)[:5])}"],
        "meme": [f"meme cues: {', '.join(find_terms(text, L.MEME_TERMS)[:5])}"],
    }[genre]
    conf = "high" if top >= 2 * max(second, 0.5) else ("medium" if top - second >= 1 else "low")
    if genre == "service_ask":
        in_nyc, _, _ = place(r)
        if in_nyc is False:
            genre = "service_ask_elsewhere"
    return genre, why, conf


def themes_for(r: Record) -> dict[str, list[str]]:
    """Theme -> matched terms. Long transcripts need 2+ distinct hits or a hit in the head."""
    head, full = _head(r), r.text + " " + " ".join("#" + h for h in r.hashtags)
    long_text = len(full) > 600
    out = {}
    for tid, t in L.THEMES.items():
        hits = find_terms(full, t["terms"])
        if not hits:
            continue
        if long_text and len(hits) < 2 and not find_terms(head, t["terms"]):
            continue
        out[tid] = hits
    return out


def duration_days(text: str) -> Optional[int]:
    best = None
    for num, unit in re.findall(L.DURATION_RE, text.lower()):
        n = int(num) if num.isdigit() else _WORD_NUM.get(num, 1)
        days = n * _UNIT_DAYS[unit]
        best = max(best or 0, days)
    return min(best, 3650) if best else None


def severity(r: Record) -> tuple[float, dict[str, list[str]], Optional[int]]:
    t = r.text
    why = {
        "hazard": find_terms(t, L.HAZARD_TERMS),
        "harm": find_terms(t, L.HARM_TERMS),
        "vulnerable": find_terms(t, L.VULNERABLE_TERMS),
        "persistence": find_terms(t, L.PERSISTENCE_TERMS),
        "frustration": find_terms(t, L.FRUSTRATION_TERMS),
        "tried_channels": find_terms(t, L.TRIED_CHANNELS_TERMS),
    }
    days = duration_days(t)
    score = (1.0 * min(len(why["hazard"]), 1) + 2.0 * min(len(why["harm"]), 2) + 1.0 * min(len(why["vulnerable"]), 2)
             + 1.0 * min(len(why["persistence"]), 2) + 0.5 * min(len(why["frustration"]), 2) + 1.5 * min(len(why["tried_channels"]), 1))
    if days:
        score += 1.0 if days < 30 else 2.0
        why["duration"] = [f"~{days} days"]
    return round(score, 1), {k: v for k, v in why.items() if v}, days


def speaker_cues(r: Record) -> dict[str, list[str]]:
    blob = r.text + " " + " ".join("#" + h for h in r.hashtags)
    return {cid: hits for cid, c in L.SPEAKER_CUES.items() if (hits := find_terms(blob, c["terms"]))}


CLOSURE_TERMS = L.CLOSURE_TERMS


def _order_themes(th: dict[str, list[str]], genre: str) -> list[str]:
    """Most-matched first; for service asks, themes with a 311 path come first (swings > 'kids')."""
    serviceable = genre in SERVICE_GENRES
    return sorted(th, key=lambda k: (serviceable and L.THEMES[k]["fit"] == "none", -len(th[k])))


def annotate(r: Record) -> Annotation:
    genre, why, conf = classify_genre(r)
    in_nyc, place_why, hint = place(r)
    th = themes_for(r)
    sev, sev_why, days = severity(r)
    quote_terms = [t for hits in th.values() for t in hits] + list(L.PROBLEM_TERMS if genre in ASK_GENRES else ())
    return Annotation(
        record=r, genre=genre, genre_why=why, genre_confidence=conf,
        in_nyc=in_nyc, place_why=place_why, place_hint=hint,
        themes=_order_themes(th, genre), theme_hits=th,
        severity=sev if genre in SERVICE_GENRES else 0.0, severity_why=sev_why if genre in SERVICE_GENRES else {},
        duration_days=days if genre in SERVICE_GENRES else None,
        cues=speaker_cues(r), quote=best_sentence(r.text, quote_terms),
        closure=find_terms(r.text, CLOSURE_TERMS),
    )
