"""Lexicon sentiment and emotional register. No LLM: a small VADER-style scorer (negation, intensifiers, emoji)
plus register word lists (frustration, hope, humor, gratitude, worry). Built for TikTok speech: profane, unpunctuated.
"""
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional

from app.services.analysis import lexicons as L
from app.services.analysis.records import Record
from app.services.analysis.textutil import find_terms, sentences

POSITIVE = {
    "love": 2, "loved": 2, "loves": 2, "great": 2, "amazing": 3, "awesome": 3, "best": 2, "good": 1, "better": 1,
    "happy": 2, "excited": 2, "proud": 2, "beautiful": 2, "wonderful": 3, "incredible": 3, "perfect": 2,
    "thank": 2, "thanks": 2, "grateful": 2, "appreciate": 2, "appreciation": 2, "goat": 2, "king": 1, "hero": 2,
    "hope": 1, "hopeful": 2, "hopefully": 1, "win": 1, "won": 1, "wholesome": 2, "cool": 1, "fun": 1, "nice": 1,
    "support": 1, "safe": 1, "fixed": 2, "helping": 1, "helps": 1, "celebrate": 2, "celebrated": 2, "refreshing": 2,
    "historic": 1, "milestone": 1, "deserve": 1, "care": 1, "cares": 1, "smart": 1, "effective": 2, "lit": 1,
    "yay": 2, "finally": 1, "sexy": 1, "hot": 1, "attractive": 1, "glad": 2, "inspiring": 2, "strong": 1,
}
NEGATIVE = {
    "hate": -2, "bad": -1, "worse": -2, "worst": -3, "terrible": -3, "horrible": -3, "awful": -3, "broken": -2,
    "dangerous": -2, "unsafe": -2, "hurt": -2, "scared": -2, "afraid": -2, "worried": -2, "concerned": -1,
    "angry": -2, "mad": -2, "pissed": -2, "tired": -1, "sick": -1, "disgusting": -3, "dirty": -2, "gross": -2,
    "liar": -3, "lied": -3, "lie": -2, "lying": -2, "fake": -2, "fraud": -3, "corrupt": -3, "compromised": -2,
    "destroy": -2, "destroying": -2, "destruction": -2, "nightmare": -2, "problem": -1, "issue": -1, "crisis": -2,
    "flood": -1, "flooding": -1, "flooded": -1, "slacking": -2, "failed": -2, "fail": -2, "failing": -2,
    "confusion": -1, "botched": -2, "blow": -1, "unacceptable": -2, "terrorist": -3, "terrorists": -3,
    "criminal": -2, "war": -1, "hostility": -2, "contamination": -2, "pollution": -2, "terrible": -3,
    "stupid": -2, "dumb": -2, "dumbest": -3, "ignorance": -2, "ridiculous": -2, "wtf": -2, "depressed": -2,
    "bored": -1, "annoying": -2, "useless": -2, "boogeyman": -1, "villain": -1,
    "racist": -2, "racism": -2, "hate crimes": -2, "propaganda": -2, "sanitizing": -1, "wet": -1, "overstimulated": -1,
}
EMOJI = {"❤️": 2, "💛": 2, "🥹": 1, "🫶": 2, "🙏": 1, "👏": 2, "😍": 3, "💐": 1, "✨": 1, "🗽": 1, "🙌": 2,
         "🥀": -1, "😔": -1, "😢": -2, "💔": -2, "😡": -3, "🤬": -3, "😤": -2}
HUMOR_EMOJI = ("😂", "🤣", "😭", "💀", "😹")
NEGATORS = {"not", "no", "never", "don't", "doesn't", "didn't", "isn't", "wasn't", "can't", "cannot", "won't", "ain't",
            "aren't", "nobody", "hasn't", "haven't"}
INTENSIFIERS = {"so": 1.3, "very": 1.3, "really": 1.3, "super": 1.4, "extremely": 1.5, "fucking": 1.5, "hella": 1.4,
                "absolutely": 1.4, "totally": 1.3, "deeply": 1.3, "most": 1.2}

REGISTERS: dict[str, dict] = {
    "frustration": {"label": "Frustration & anger", "terms": L.FRUSTRATION_TERMS + (
        "tired", "sick and tired", "pissed", "angry", "ridiculous", "slacking", "nothing is getting done",
        "still hasn't", "hasn't been fixed", "liar", "lied", "unacceptable", "i'm sick")},
    "hope": {"label": "Hope & optimism", "terms": tuple(t for t in L.HOPE_TERMS if t != "please") + (
        "hope", "hopeful", "can't wait", "excited", "finally", "looking forward", "new era", "dream", "believe")},
    "humor": {"label": "Humor & play", "terms": ("lol", "lmao", "lmfao", "haha", "joke", "joking", "jk", "meme",
                                                  "bikini bottom", "magically") + HUMOR_EMOJI},
    "gratitude": {"label": "Gratitude & praise", "terms": ("thank you", "thanks", "grateful", "appreciate",
                                                            "appreciation", "goat", "my mayor", "our mayor", "👏", "🫶")},
    "worry": {"label": "Worry & safety", "terms": ("scared", "afraid", "worried", "concerned", "dangerous", "unsafe",
                                                    "get hurt", "someone's gonna get hurt", "threat", "hate crimes",
                                                    "can't breathe", "contamination")},
}
_TOK = re.compile(r"[a-z][a-z'’]*|[^\w\s]", re.I)


@dataclass
class Tone:
    compound: float
    label: str  # positive | negative | mixed | neutral
    pos_hits: list[str]
    neg_hits: list[str]
    registers: dict[str, list[str]]


def _score_tokens(text: str) -> tuple[float, float, list[str], list[str]]:
    toks = [t.lower().replace("’", "'") for t in _TOK.findall(text)]
    pos = neg = 0.0
    pos_hits, neg_hits = [], []
    for i, t in enumerate(toks):
        v = POSITIVE.get(t) or NEGATIVE.get(t)
        if not v:
            continue
        window = toks[max(0, i - 3):i]
        if any(w in NEGATORS for w in window):
            v = -0.75 * v
        boost = max([INTENSIFIERS.get(w, 1.0) for w in toks[max(0, i - 2):i]] or [1.0])
        v *= boost
        if v > 0:
            pos += v
            pos_hits.append(t)
        else:
            neg += v
            neg_hits.append(t)
    for e, v in EMOJI.items():
        c = text.count(e)
        if c:
            (pos_hits if v > 0 else neg_hits).append(e)
            if v > 0:
                pos += v * min(c, 3)
            else:
                neg += v * min(c, 3)
    return pos, neg, pos_hits, neg_hits


def tone(text: str) -> Tone:
    pos, neg, ph, nh = _score_tokens(text)
    raw = pos + neg
    words = max(len(text.split()), 1)
    raw = raw / math.sqrt(1 + words / 40)  # long monologues shouldn't saturate just by length
    compound = raw / math.sqrt(raw * raw + 15)
    if len(ph) >= 2 and len(nh) >= 2 and abs(compound) < 0.35:
        label = "mixed"
    elif compound >= 0.2:
        label = "positive"
    elif compound <= -0.2:
        label = "negative"
    else:
        label = "neutral"
    regs = {rid: hits for rid, r in REGISTERS.items() if (hits := find_terms(text, r["terms"]))}
    return Tone(round(compound, 3), label, ph, nh, regs)


def register_sentence(text: str, terms) -> Optional[str]:
    for s in sentences(text):
        if find_terms(s, terms):
            return s
    return None
