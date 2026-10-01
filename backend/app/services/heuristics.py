"""Keyword fallback extractor used when GEMINI_API_KEY is not set. Deliberately conservative:
everything it produces is low-confidence and flagged for human review."""
import re
from typing import Any, Optional

from app.services.gemini_service import normalize_observation
from app.utils.constants import BOROUGHS, TOPIC_KEYWORDS

NEIGHBORHOODS = {
    "Manhattan": ["Harlem", "East Harlem", "Washington Heights", "Inwood", "Upper West Side", "Upper East Side",
                  "Midtown", "Chelsea", "Hell's Kitchen", "Lower East Side", "East Village", "West Village",
                  "SoHo", "Tribeca", "Chinatown", "Financial District", "Murray Hill", "Gramercy", "Hamilton Heights"],
    "Brooklyn": ["Bed-Stuy", "Bedford-Stuyvesant", "Bushwick", "Williamsburg", "Greenpoint", "Crown Heights",
                 "Flatbush", "Park Slope", "Prospect Heights", "Sunset Park", "Bay Ridge", "Bensonhurst",
                 "Brownsville", "East New York", "Canarsie", "Coney Island", "Red Hook", "Fort Greene",
                 "Clinton Hill", "Borough Park", "Sheepshead Bay", "Flatlands", "Gowanus", "Ditmas Park"],
    "Queens": ["Astoria", "Long Island City", "Jackson Heights", "Elmhurst", "Corona", "Flushing", "Jamaica",
               "Ridgewood", "Sunnyside", "Woodside", "Forest Hills", "Rego Park", "Far Rockaway", "Rockaway",
               "Richmond Hill", "Ozone Park", "Bayside", "Maspeth"],
    "Bronx": ["Mott Haven", "Hunts Point", "Fordham", "Riverdale", "Pelham Bay", "Co-op City", "Parkchester",
              "Soundview", "Morris Park", "Highbridge", "Kingsbridge", "Throgs Neck", "Tremont", "Belmont"],
    "Staten Island": ["St. George", "Stapleton", "Tottenville", "Great Kills", "New Dorp", "Port Richmond"],
}
BOROUGH_ALIASES = {"bk": "Brooklyn", "bklyn": "Brooklyn", "the bronx": "Bronx", "bx": "Bronx",
                   "si": "Staten Island", "manhattan": "Manhattan", "queens": "Queens", "brooklyn": "Brooklyn",
                   "bronx": "Bronx", "staten island": "Staten Island"}
STREET = r"(?:[A-Z0-9][\w'.]*\s){0,3}(?:Ave(?:nue)?|St(?:reet)?|Blvd|Boulevard|Pkwy|Parkway|Rd|Road|Pl|Place|Broadway|Concourse)\b"
INTERSECTION_RE = re.compile(rf"({STREET})\s*(?:&|and|at|/)\s*({STREET})")
ADDRESS_RE = re.compile(rf"\b(\d{{1,5}}\s{STREET})")
STREET_RE = re.compile(rf"\b(?:on|at|near)\s+({STREET})")
URGENT_WORDS = ("dangerous", "unsafe", "emergency", "hurt", "injured", "fell", "kids", "children", "flooding", "fire")
REQUEST_WORDS = ("fix", "please", "help", "can you", "need")


def _find_location(text: str) -> tuple[Optional[str], float]:
    for regex, conf in ((ADDRESS_RE, 0.6), (INTERSECTION_RE, 0.55), (STREET_RE, 0.4)):
        m = regex.search(text)
        if m:
            return (" & ".join(g.strip() for g in m.groups()) if regex is INTERSECTION_RE else m.group(1).strip()), conf
    return None, 0.0


def _find_area(text: str) -> tuple[Optional[str], Optional[str]]:
    low = text.lower()
    for borough, names in NEIGHBORHOODS.items():
        for name in names:
            if re.search(rf"\b{re.escape(name.lower())}\b|#{re.escape(name.lower().replace(' ', '').replace('-', ''))}\b", low):
                return name, borough
    for alias, borough in BOROUGH_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b|#{alias.replace(' ', '')}\b", low):
            return None, borough
    return None, None


def _quote(text: str, keywords: tuple[str, ...]) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]
    for sentence in sentences:  # prefer a sentence naming the problem
        if any(re.search(rf"\b{re.escape(k)}\b", sentence.lower()) for k in keywords):
            return sentence[:240]
    return ""


LABEL_RE = re.compile(r"^(Caption|Location tag on post|On-screen text|Spoken \(TikTok captions\)|Captions|Spoken transcript):\s*", re.M)


def extract(content: str, language: str = "en") -> dict[str, Any]:
    content = LABEL_RE.sub("", content)
    low = content.lower()
    scores = {t: sum(len(re.findall(rf"\b{re.escape(k)}\b", low)) for k in kws) for t, kws in TOPIC_KEYWORDS.items()}
    topic, hits = max(scores.items(), key=lambda kv: kv[1])
    if hits == 0:
        topic = "other"
    location, loc_conf = _find_location(content)
    neighborhood, borough = _find_area(content)
    if location is None and neighborhood:
        loc_conf = 0.35
    kws = TOPIC_KEYWORDS.get(topic, ())
    is_request = any(w in low for w in REQUEST_WORDS)
    raw = {
        "type": ("request" if is_request else "issue") if topic != "other" else "other",
        "topic": topic,
        "summary": _quote(content, kws) or content.strip().split("\n")[0][:240],
        "location_description": location,
        "borough": borough if borough in BOROUGHS else None,
        "neighborhood": neighborhood,
        "location_confidence": loc_conf,
        "agency_candidates": [],
        "urgency": "high" if any(w in low for w in URGENT_WORDS) else ("medium" if topic != "other" else None),
        "language": language,
        "confidence": min(0.45, 0.2 + 0.08 * hits),  # never above the needs-review threshold
        "evidence": {"quote": _quote(content, kws) or _quote(content, ("fix",))},
    }
    out = normalize_observation(raw, language)
    out["summary"] = f"[keyword draft — needs review] {out['summary']}"
    return out
