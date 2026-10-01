"""Echoes: which stories travelled across many creators, and which problems are being reported more than once.

1. Narrative waves: average-linkage agglomerative clustering of TF-IDF vectors over every transcript. A wave is
   a cluster spanning 2+ distinct creators. Each wave reports who carried it (news vs residents), reach and span.
2. Same-issue groups among service asks: same theme within a time window, from different creators.
3. Closure signals: videos that say something got fixed, linked to earlier asks on the same theme.
"""
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from app.services.analysis import lexicons as L
from app.services.analysis.annotate import SERVICE_GENRES, Annotation
from app.services.analysis.textutil import STOPWORDS, cosine, tfidf, tokens

WAVE_THRESHOLD = 0.10  # average cosine similarity needed to merge clusters (tuned by hand on the Sept corpus)
SAME_ISSUE_WINDOW = timedelta(days=4)
MIN_WAVE_CREATORS = 3
MAX_WAVE_DOCS = 500
# Words that tie videos together without sharing a story (profanity, the mayor's tag/name variants, filler).
WAVE_STOP = frozenset("""
new york city yorkers people time today year kwame pls bro fuck fucking shit ass dude cause think feel something
everybody zohranmamdani nyclife nyctiktok nycmayor momdani mandani mondani madani donnie mom man will end post bad
know need good great look yall y'all guy guys gonna talking
""".split())


def _when(a: Annotation) -> datetime:
    return a.record.posted_at or datetime.min


def _cluster(vecs: list[dict[str, float]], threshold: float) -> list[list[int]]:
    """Average-linkage agglomerative clustering with Lance-Williams updates (pure Python, O(n^2) per merge)."""
    idx = [i for i, v in enumerate(vecs) if v]
    n = len(idx)
    sim = [[0.0] * n for _ in range(n)]
    for a in range(n):
        for b in range(a + 1, n):
            sim[a][b] = sim[b][a] = cosine(vecs[idx[a]], vecs[idx[b]])
    members = {a: [idx[a]] for a in range(n)}
    while len(members) > 1:
        best, pair = threshold, None
        keys = list(members)
        for x, a in enumerate(keys):
            row = sim[a]
            for b in keys[x + 1:]:
                if row[b] > best:
                    best, pair = row[b], (a, b)
        if pair is None:
            break
        a, b = pair
        na, nb = len(members[a]), len(members[b])
        for k in members:
            if k not in (a, b):
                sim[a][k] = sim[k][a] = (na * sim[a][k] + nb * sim[b][k]) / (na + nb)
        members[a] += members.pop(b)
    return list(members.values())


def _top_terms(members: list[int], vecs: list[dict[str, float]], n: int = 6) -> list[str]:
    acc: Counter = Counter()
    for i in members:
        acc.update(vecs[i])
    return [t for t, _ in acc.most_common(n)]


def _wave_theme(anns: list[Annotation]) -> Optional[str]:
    """A wave is 'named' when at least half its videos share a lexicon theme; else it's a loose word overlap."""
    themes = Counter(t for a in anns for t in a.themes[:2])
    if themes:
        tid, n = themes.most_common(1)[0]
        if n >= max(2, (len(anns) + 1) // 2):
            return tid
    return None


def narrative_waves(anns: list[Annotation], threshold: float = WAVE_THRESHOLD) -> list[dict]:
    anns = sorted(anns, key=_when)[-MAX_WAVE_DOCS:]  # keep clustering interactive as the DB grows
    stop = STOPWORDS | WAVE_STOP
    docs = [tokens(a.record.text, stop) for a in anns]
    vecs, _ = tfidf(docs, min_df=2)
    waves = []
    for members in _cluster(vecs, threshold):
        group = [anns[i] for i in members]
        creators = {a.record.handle for a in group}
        if len(creators) < MIN_WAVE_CREATORS:
            continue
        group.sort(key=_when)
        dated = [a.record.posted_at for a in group if a.record.posted_at]
        genres = Counter(a.genre for a in group)
        news = sum(1 for a in group if a.genre == "news_official")
        views = sum(a.record.views for a in group)
        terms = _top_terms(members, vecs)
        tid = _wave_theme(group)
        waves.append({
            "label": L.THEMES[tid]["label"] if tid else " · ".join(terms[:3]),
            "theme": tid,
            "named": tid is not None,
            "terms": terms,
            "videos": len(group),
            "creators": len(creators),
            "news_or_official": news,
            "residents_and_others": len(group) - news,
            "views": views,
            "views_via_news": sum(a.record.views for a in group if a.genre == "news_official"),
            "genres": dict(genres.most_common()),
            "first_at": dated[0].isoformat() + "Z" if dated else None,
            "last_at": dated[-1].isoformat() + "Z" if dated else None,
            "span_hours": round((dated[-1] - dated[0]).total_seconds() / 3600, 1) if len(dated) > 1 else 0,
            "first_by": group[0].record.handle,
            "member_ids": [a.record.id for a in group],
            "members": [{"handle": a.record.handle, "url": a.record.url, "genre": a.genre, "views": a.record.views,
                         "posted_at": a.record.posted_at.isoformat() + "Z" if a.record.posted_at else None,
                         "quote": a.quote} for a in group],
        })
    waves.sort(key=lambda w: (w["creators"], w["views"]), reverse=True)
    return waves


def same_issue_groups(anns: list[Annotation]) -> list[dict]:
    asks = [a for a in anns if a.genre in SERVICE_GENRES and a.themes]
    groups = []
    for tid in L.THEMES:
        members = sorted((a for a in asks if a.themes[0] == tid),
                         key=_when)
        # split into time windows so a pothole in March and one in September are not "the same wave"
        window: list[Annotation] = []
        for a in members + [None]:
            if a is not None and (not window or (a.record.posted_at and window[-1].record.posted_at
                                                 and a.record.posted_at - window[-1].record.posted_at <= SAME_ISSUE_WINDOW)):
                window.append(a)
                continue
            if len({w.record.handle for w in window}) >= 2:
                groups.append(_issue_group(tid, window))
            window = [a] if a is not None else []
    groups.sort(key=lambda g: g["videos"], reverse=True)
    return groups


def _issue_group(tid: str, window: list[Annotation]) -> dict:
    places = [a.place_hint for a in window if a.place_hint]
    return {
        "theme": tid, "label": L.THEMES[tid]["label"], "videos": len(window),
        "creators": len({a.record.handle for a in window}),
        "places": places, "in_nyc": sum(1 for a in window if a.in_nyc), "views": sum(a.record.views for a in window),
        "first_at": window[0].record.posted_at.isoformat() + "Z" if window[0].record.posted_at else None,
        "last_at": window[-1].record.posted_at.isoformat() + "Z" if window[-1].record.posted_at else None,
        "members": [{"handle": a.record.handle, "url": a.record.url, "place": a.place_hint, "quote": a.quote,
                     "in_nyc": a.in_nyc} for a in window],
        "note": "Same theme and time window, different creators. Different places mean a pattern, not a duplicate.",
    }


def closures(anns: list[Annotation]) -> list[dict]:
    """'He fixed it' videos, each with up to 3 earlier asks on the same theme as *candidate* matches.

    Matching is by shared theme and time order only, so a human must confirm a link before it counts as closed.
    """
    asks = [a for a in anns if a.genre in SERVICE_GENRES]
    out = []
    for a in sorted((a for a in anns if a.genre == "response"), key=_when):
        prior = [b for b in asks if _when(b) < _when(a) and set(b.themes) & set(a.themes)]
        prior.sort(key=lambda b: (b.in_nyc is not True, -len(set(b.themes) & set(a.themes)), _when(a) - _when(b)))
        out.append({
            "handle": a.record.handle, "url": a.record.url, "posted_at": a.record.posted_at.isoformat() + "Z"
            if a.record.posted_at else None, "views": a.record.views, "said": a.closure or a.genre_why,
            "quote": a.quote, "themes": a.themes,
            "candidate_asks": [{"handle": b.record.handle, "url": b.record.url, "quote": b.quote,
                                "posted_at": b.record.posted_at.isoformat() + "Z" if b.record.posted_at else None,
                                "shared_themes": sorted(set(b.themes) & set(a.themes))} for b in prior[:3]],
        })
    return out


COPY_THRESHOLD = 0.85


def duplicate_scripts(anns: list[Annotation], threshold: float = COPY_THRESHOLD) -> list[dict]:
    """Near-identical spoken/written text posted by *different* creators (reposts, templates, copypasta).

    These should not be counted as independent voices. Being flagged here is not proof of coordination.
    """
    pool = [a for a in anns if len(a.record.text.split()) >= 12]
    docs = [tokens(a.record.speech or a.record.text, STOPWORDS) for a in pool]
    vecs, _ = tfidf(docs, min_df=1)
    parent = list(range(len(pool)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            if pool[i].record.handle != pool[j].record.handle and cosine(vecs[i], vecs[j]) >= threshold:
                parent[find(i)] = find(j)
    groups: dict[int, list[Annotation]] = {}
    for i, a in enumerate(pool):
        groups.setdefault(find(i), []).append(a)
    out = []
    for g in groups.values():
        handles = {a.record.handle for a in g}
        if len(handles) < 2:
            continue
        g.sort(key=_when)
        out.append({
            "videos": len(g), "creators": len(handles), "views": sum(a.record.views for a in g),
            "quote": g[0].quote, "genres": dict(Counter(a.genre for a in g)),
            "members": [{"handle": a.record.handle, "url": a.record.url, "views": a.record.views,
                         "posted_at": a.record.posted_at.isoformat() + "Z" if a.record.posted_at else None} for a in g],
        })
    out.sort(key=lambda d: -d["videos"])
    return out
