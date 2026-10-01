"""Tiny dependency-free text toolkit: tokenizing, TF-IDF vectors, cosine, sentence picking."""
import math
import re
from collections import Counter
from typing import Iterable, Optional

STOPWORDS = frozenset("""
a about above after again against all am an and any are aren't as at be because been before being below between
both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from
further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his how
how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off
on once only or other ought our ours ourselves out over own same shan't she she'd she'll she's should shouldn't so
some such than that that's the their theirs them themselves then there there's these they they'd they'll they're
they've this those through to too under until up very was wasn't we we'd we'll we're we've were weren't what what's
when when's where where's which while who who's whom why why's with won't would wouldn't you you'd you'll you're
you've your yours yourself yourselves im ive dont cant wont thats youre theyre gonna wanna gotta like just really
get got go going know yeah oh okay ok um uh so literally actually also even still one thing things right lot
want see say said come make way thing us let's na la de el que en y es lo por un una los las se del con para
mamdani zohran mayor fyp foryou foryoupage viral nyc newyork newyorkcity tiktok hey fix fixthis mamdanifixthis
mamdanifixit fixitmamdani fixthismamdani heymamdani please
""".split())

_TOKEN_RE = re.compile(r"[a-z][a-z'’]+")
_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n+| / ")


def tokens(text: str, stop: frozenset = STOPWORDS) -> list[str]:
    toks = [t.replace("’", "'").strip("'") for t in _TOKEN_RE.findall(text.lower())]
    return [t for t in toks if len(t) > 2 and t not in stop]


def sentences(text: str, max_len: int = 260) -> list[str]:
    """Split into quotable chunks. TikTok ASR often has no punctuation, so long runs are windowed."""
    out: list[str] = []
    for chunk in _SENT_RE.split(text or ""):
        chunk = chunk.strip(" -–—")
        if not chunk:
            continue
        words = chunk.split()
        step = 40
        for i in range(0, len(words), step):
            piece = " ".join(words[i:i + step])
            if len(piece) >= 12:
                out.append(piece[:max_len])
    return out


def tfidf(docs: list[list[str]], min_df: int = 2) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Returns L2-normalised sparse vectors and the idf table. Terms in < min_df docs are dropped."""
    df = Counter(t for d in docs for t in set(d))
    n = len(docs)
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items() if c >= min_df}
    vecs = []
    for d in docs:
        tf = Counter(t for t in d if t in idf)
        v = {t: (1 + math.log(c)) * idf[t] for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs, idf


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def find_terms(text: str, terms: Iterable[str]) -> list[str]:
    """Which lexicon entries occur as whole words/phrases (case-insensitive)."""
    low = text.lower()
    return [t for t in terms if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", low)]


def best_sentence(text: str, terms: Iterable[str], fallback: bool = True) -> Optional[str]:
    """The sentence with most lexicon hits; used to pull a representative quote."""
    terms = list(terms)
    best, score = None, 0
    for s in sentences(text):
        hits = len(find_terms(s, terms))
        if hits > score:
            best, score = s, hits
    if best is None and fallback:
        ss = sentences(text)
        best = ss[0] if ss else None
    return best
