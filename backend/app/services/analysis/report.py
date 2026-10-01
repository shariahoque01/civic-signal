"""Assemble every insights section from normalized records. Pure functions + a small fingerprint cache."""
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.analysis import echoes, ome, sentiment
from app.services.analysis import lexicons as L
from app.services.analysis.annotate import ASK_GENRES, GENRES, SERVICE_GENRES, Annotation, annotate
from app.services.analysis.records import CORPUS_PATH, Record, load_records
from app.services.analysis.textutil import STOPWORDS, tfidf, tokens

FIT_BUCKETS = {
    "drafts_cleanly": "311 type exists and Civic Signal can draft it",
    "311_not_in_app": "311 has a type, but Civic Signal's taxonomy doesn't draft it yet",
    "outside_nyc": "Outside NYC jurisdiction (trend copied elsewhere)",
    "no_311_path": "No 311 path: personal, school, or policy ask",
    "needs_viewing": "Can't tell from text; a person must watch the video",
}
CAVEATS = [
    "Small, hashtag-sampled corpus: these are the videos found by searching a handful of tags over {days} days, "
    "not a representative sample of New Yorkers or of TikTok.",
    "Every label here comes from transparent keyword rules and statistics, not from a model, and can be wrong. "
    "The 'why' fields show which words fired.",
    "Speech comes from TikTok's own auto-captions, which exist for only some videos. Silent videos are judged on "
    "caption and on-screen text alone.",
    "Speaker cues are only what people say about themselves (\"I'm a teacher\"). Nothing is inferred about anyone's "
    "identity, age or protected traits.",
    "View counts are a snapshot at fetch time and favor older posts.",
    "Public posts only, creator handles only. This is for surfacing feedback to fix services, not for monitoring people.",
]
_cache: dict[tuple, dict] = {}


def load(source: str = "auto") -> tuple[list[Record], str]:
    return load_records(source)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _place_name(hint: str) -> str:
    """'UH-Downtown, Houston, TX 77002, USA' -> 'Houston'; 'beverly hills' -> 'Beverly Hills'."""
    parts = [p.strip() for p in hint.split(",")]
    name = parts[1] if len(parts) > 2 else parts[0]
    return name.title() if name.islower() else name


def _span(hours: float) -> str:
    return f"{hours:.0f} hours" if hours < 72 else f"{hours / 24:.0f} days"


def _median(xs: list[int]) -> int:
    return int(statistics.median(xs)) if xs else 0


def _pctile(value: int, population: list[int]) -> int:
    if not population:
        return 0
    return round(100 * sum(1 for p in population if p <= value) / len(population))


def _card(a: Annotation, **extra: Any) -> dict:
    r = a.record
    return {
        "handle": r.handle, "url": r.url, "posted_at": _iso(r.posted_at), "views": r.views, "likes": r.likes,
        "genre": a.genre, "genre_label": GENRES[a.genre]["label"], "quote": a.quote,
        "themes": a.themes, "has_speech": r.has_speech, **extra,
    }


# --- sections ----------------------------------------------------------------------------------------------
def genres_section(anns: list[Annotation]) -> dict:
    total_views = sum(a.record.views for a in anns) or 1
    by: dict[str, list[Annotation]] = defaultdict(list)
    for a in anns:
        by[a.genre].append(a)
    rows = []
    for gid, meta in GENRES.items():
        group = by.get(gid, [])
        views = [a.record.views for a in group]
        examples = sorted(group, key=lambda a: -a.record.views)[:3]
        rows.append({
            "id": gid, **meta, "count": len(group), "views": sum(views), "median_views": _median(views),
            "share_of_videos": round(len(group) / max(len(anns), 1), 3),
            "share_of_views": round(sum(views) / total_views, 3), "is_ask": gid in ASK_GENRES,
            "low_confidence": sum(1 for a in group if a.genre_confidence == "low"),
            "examples": [_card(a, why=a.genre_why) for a in examples],
        })
    days: dict[str, Counter] = defaultdict(Counter)
    for a in anns:
        if a.record.posted_at:
            days[a.record.posted_at.date().isoformat()][a.genre] += 1
    timeline = [{"date": d, "total": sum(c.values()), "counts": dict(c)} for d, c in sorted(days.items())]

    tag_rows: dict[str, list[Annotation]] = defaultdict(list)
    for a in anns:
        tags = set(a.record.discovered_via) or {"#" + h for h in a.record.hashtags}
        for t in tags:
            tag_rows["#" + t.lstrip("#")].append(a)
    hashtag_yield = sorted(
        ({"tag": t, "videos": len(g), "service_asks": sum(1 for a in g if a.genre in SERVICE_GENRES),
          "nyc_service_asks": sum(1 for a in g if a.genre == "service_ask"),
          "yield": round(sum(1 for a in g if a.genre == "service_ask") / len(g), 2)}
         for t, g in tag_rows.items() if len(g) >= 3),
        key=lambda x: (-x["yield"], -x["videos"]),
    )[:12]
    agreement = None
    labelled = [a for a in anns if a.record.relevance]
    if labelled:  # cross-check against the ingest pipeline's own relevance label, when the DB has one
        table = Counter((a.record.relevance, "ask" if a.genre in SERVICE_GENRES else "other") for a in labelled)
        fix = [a for a in labelled if a.record.relevance == "fix_request"]
        agreement = {
            "labelled": len(labelled),
            "crosstab": [{"relevance": k[0], "ours": k[1], "count": v} for k, v in sorted(table.items())],
            "fix_requests_we_call_asks": round(sum(1 for a in fix if a.genre in SERVICE_GENRES) / len(fix), 2)
            if fix else None,
            "note": "Compares this page's rule-based genre with the 'relevance' label set at ingest. Neither is "
                    "ground truth; disagreements are the videos worth a human look.",
        }
    return {"rows": rows, "timeline": timeline, "hashtag_yield": hashtag_yield, "agreement": agreement,
            "hashtag_basis": "discovered_via search tags when known, else the post's own hashtags"}


def _fit_bucket(a: Annotation) -> str:
    if a.genre == "visual_ask" or (a.genre in SERVICE_GENRES and not a.themes):
        return "needs_viewing"
    if a.genre == "service_ask_elsewhere" or a.in_nyc is False:
        return "outside_nyc"
    if a.genre == "personal_ask":
        return "no_311_path"
    fit = L.THEMES[a.themes[0]]["fit"]
    return {"app": "drafts_cleanly", "311": "311_not_in_app"}.get(fit, "no_311_path")


def themes_section(anns: list[Annotation]) -> dict:
    rows = []
    for tid, t in L.THEMES.items():
        group = [a for a in anns if tid in a.themes]
        if not group:
            continue
        group.sort(key=lambda a: (-(a.genre in ASK_GENRES), -len(a.theme_hits.get(tid, [])), -a.record.views))
        dated = sorted(a.record.posted_at for a in group if a.record.posted_at)
        rows.append({
            "id": tid, "label": t["label"], "fit": t["fit"], "sr_hint": t["sr_hint"], "videos": len(group),
            "creators": len({a.record.handle for a in group}), "views": sum(a.record.views for a in group),
            "asks": sum(1 for a in group if a.genre in ASK_GENRES),
            "genres": dict(Counter(a.genre for a in group).most_common()),
            "first_at": _iso(dated[0]) if dated else None, "last_at": _iso(dated[-1]) if dated else None,
            "quotes": [_card(a, matched=a.theme_hits[tid]) for a in group[:3]],
        })
    rows.sort(key=lambda r: (-r["videos"], -r["views"]))

    asks = [a for a in anns if a.genre in ASK_GENRES]
    buckets: dict[str, list[dict]] = {k: [] for k in FIT_BUCKETS}
    for a in sorted(asks, key=lambda a: -a.severity):
        b = _fit_bucket(a)
        buckets[b].append(_card(a, place=a.place_hint, primary_theme=a.themes[0] if a.themes else None,
                                sr_hint=L.THEMES[a.themes[0]]["sr_hint"] if a.themes else None))
    fit_gap = [{"id": k, "label": v, "count": len(buckets[k]), "items": buckets[k]} for k, v in FIT_BUCKETS.items()]

    unthemed = [a for a in anns if not a.themes and a.genre != "off_topic"]
    vocab: list[str] = []
    if unthemed:
        vecs, _ = tfidf([tokens(a.record.text, STOPWORDS | echoes.WAVE_STOP) for a in unthemed], min_df=2)
        acc: Counter = Counter()
        for v in vecs:
            acc.update(v)
        vocab = [t for t, _ in acc.most_common(15)]
    return {"rows": rows, "fit_gap": fit_gap, "asks_total": len(asks),
            "unthemed": {"count": len(unthemed), "top_terms": vocab,
                         "note": "Videos no theme lexicon matched; their recurring words are candidates for new themes."}}


def attention_section(anns: list[Annotation]) -> dict:
    views_all = [a.record.views for a in anns]
    median_all = _median(views_all)
    service = [a for a in anns if a.genre in SERVICE_GENRES]
    nyc = [a for a in service if a.genre == "service_ask"]
    items = []
    for a in sorted(service, key=lambda a: (-a.severity, a.record.views)):
        pct = _pctile(a.record.views, views_all)
        quadrant = ("quiet but serious" if a.severity >= 2 and a.record.views < median_all else
                    "loud and serious" if a.severity >= 2 else
                    "loud, lower stakes" if a.record.views >= median_all else "quiet, lower stakes")
        items.append(_card(a, severity=a.severity, severity_why=a.severity_why, duration_days=a.duration_days,
                           views_percentile=pct, quadrant=quadrant, in_nyc=a.in_nyc, place=a.place_hint))
    by_genre = {g: _median([a.record.views for a in anns if a.genre == g]) for g in GENRES}
    tried = [a for a in service if a.severity_why.get("tried_channels")]
    return {
        "corpus_median_views": median_all,
        "median_views_by_genre": by_genre,
        "service_asks": len(service), "nyc_service_asks": len(nyc),
        "service_ask_share_of_views": round(sum(a.record.views for a in service) / max(sum(views_all), 1), 4),
        "items": items,
        "quiet_but_serious": [i for i in items if i["quadrant"] == "quiet but serious"],
        "tried_official_channels": [_card(a, said=a.severity_why["tried_channels"]) for a in tried],
        "severity_method": "hazard words +1, harm words +2 each (max 2), vulnerable people +1 each (max 2), "
                           "persistence +1 each (max 2), frustration +0.5 each (max 2), says they already used "
                           "311/community board +1.5, stated duration +1 (<30 days) or +2.",
    }


def voices_section(anns: list[Annotation]) -> dict:
    n = max(len(anns), 1)
    with_speech = [a for a in anns if a.record.has_speech]
    on_screen_only = [a for a in anns if not a.record.has_speech and a.record.on_screen]
    caption_only = [a for a in anns if not a.record.has_speech and not a.record.on_screen]
    asks = [a for a in anns if a.genre in ASK_GENRES]
    langs = Counter((a.record.language or "unknown") for a in with_speech)
    cues = []
    for cid, c in L.SPEAKER_CUES.items():
        group = [a for a in anns if cid in a.cues]
        if group:
            cues.append({"id": cid, "label": c["label"], "count": len(group),
                         "examples": [_card(a, matched=a.cues[cid]) for a in group[:4]]})
    cues.sort(key=lambda c: -c["count"])
    return {
        "coverage": {"with_speech": len(with_speech), "on_screen_text_only": len(on_screen_only),
                     "caption_only": len(caption_only), "share_with_speech": round(len(with_speech) / n, 3)},
        "asks_without_speech": sum(1 for a in asks if not a.record.has_speech), "asks": len(asks),
        "speech_languages": dict(langs.most_common()),
        "location_tagged": sum(1 for a in anns if a.record.location_tag),
        "cues": cues,
        "note": "Self-described only. We count what people say about themselves; we never infer who they are.",
    }


def quotes_section(anns: list[Annotation]) -> dict:
    items = [
        _card(a, severity=a.severity, place=a.place_hint)
        for a in sorted(anns, key=lambda a: (-(a.genre in ASK_GENRES), -a.severity, -a.record.views))
        if a.quote and a.genre != "off_topic"
    ]
    return {"total": len(items), "items": items}


def sentiment_section(anns: list[Annotation], tones: dict[str, sentiment.Tone]) -> dict:
    def agg(group: list[Annotation]) -> dict:
        ts = [tones[a.record.id] for a in group]
        c = Counter(t.label for t in ts)
        n = max(len(ts), 1)
        regs = Counter(r for t in ts for r in t.registers)
        return {"n": len(ts), "mean": round(sum(t.compound for t in ts) / n, 3),
                **{k: c.get(k, 0) for k in ("positive", "negative", "mixed", "neutral")},
                "top_register": regs.most_common(1)[0][0] if regs else None}

    by_theme = [{"theme": tid, "label": L.THEMES[tid]["label"], **agg(g)}
                for tid in L.THEMES if len(g := [a for a in anns if tid in a.themes]) >= 2]
    by_theme.sort(key=lambda r: r["mean"])
    by_genre = [{"genre": gid, "label": GENRES[gid]["label"], **agg(g)}
                for gid in GENRES if (g := [a for a in anns if a.genre == gid])]
    days: dict[str, list[Annotation]] = defaultdict(list)
    for a in anns:
        if a.record.posted_at:
            days[a.record.posted_at.date().isoformat()].append(a)
    over_time = [{"date": d, **agg(g)} for d, g in sorted(days.items())]
    registers = []
    for rid, reg in sentiment.REGISTERS.items():
        group = [a for a in anns if rid in tones[a.record.id].registers and a.genre != "off_topic"]
        group.sort(key=lambda a: (-(a.genre in ASK_GENRES), -len(tones[a.record.id].registers[rid]), -a.record.views))
        registers.append({
            "id": rid, "label": reg["label"], "count": len(group), "share": round(len(group) / max(len(anns), 1), 3),
            "by_genre": dict(Counter(a.genre for a in group).most_common(4)),
            "quotes": [_card(a, quote=sentiment.register_sentence(a.record.text, reg["terms"]) or a.quote,
                             matched=tones[a.record.id].registers[rid][:4]) for a in group[:5]],
        })
    ranked = sorted((a for a in anns if a.genre != "off_topic"), key=lambda a: tones[a.record.id].compound)
    tcard = lambda a: _card(a, compound=tones[a.record.id].compound, label=tones[a.record.id].label,  # noqa: E731
                            pos_words=tones[a.record.id].pos_hits[:5], neg_words=tones[a.record.id].neg_hits[:5])
    asks = [a for a in anns if a.genre in ASK_GENRES]
    return {
        "overall": agg([a for a in anns if a.genre != "off_topic"]),
        "asks": agg(asks) if asks else None,
        "by_theme": by_theme, "by_genre": by_genre, "over_time": over_time, "registers": registers,
        "most_negative": [tcard(a) for a in ranked[:5]], "most_positive": [tcard(a) for a in ranked[::-1][:5]],
        "method": "Lexicon scorer in the style of VADER: about 200 weighted words and emoji, negation flips "
                  "within 3 words, intensifiers (so, really, f***ing) boost, length-damped, squashed to [-1, 1]. "
                  "positive >= 0.2, negative <= -0.2, mixed = 2+ hits each way near zero. Registers are word lists.",
        "caveat": "Lexicons miss sarcasm, slang and context. 'Negative' often means upset about a problem, not about "
                  "the mayor. Read the quotes.",
    }


def overview_section(anns: list[Annotation], sections: dict) -> dict:
    views = sum(a.record.views for a in anns)
    service = [a for a in anns if a.genre in SERVICE_GENRES]
    nyc = [a for a in anns if a.genre == "service_ask"]
    att = sections["attention"]
    med = att["median_views_by_genre"]
    named_waves = [w for w in sections["echoes"]["waves"] if w["named"]]
    tiles = [
        {"value": len(anns), "label": "videos analysed"},
        {"value": len({a.record.handle for a in anns}), "label": "distinct creators"},
        {"value": views, "label": "total views", "format": "compact"},
        {"value": len(nyc), "label": "NYC service asks"},
        {"value": round(100 * att["service_ask_share_of_views"], 1), "label": "% of views going to service asks",
         "format": "pct"},
        {"value": len(att["quiet_but_serious"]), "label": "quiet-but-serious asks"},
        {"value": sum(1 for a in anns if a.genre == "response"), "label": "\"he fixed it\" videos"},
    ]
    headlines = []
    if anns:
        headlines.append(f"Only {len(service)} of {len(anns)} videos ({round(100 * len(service) / len(anns))}%) "
                         f"ask for a fixable problem, and just {len(nyc)} both name the problem and are in NYC. "
                         f"The tag mostly carries commentary, news and fandom.")
    if nyc and med.get("news_official"):
        headlines.append(f"Median views: NYC service asks {med['service_ask']:,} vs news/official "
                         f"{med['news_official']:,} vs commentary {med['commentary']:,}.")
    elsewhere = [a for a in anns if a.genre == "service_ask_elsewhere"]
    if elsewhere:
        places = ", ".join(sorted({_place_name(a.place_hint) for a in elsewhere if a.place_hint}))
        headlines.append(f"{len(elsewhere)} of {len(service)} service asks are outside NYC ({places}). "
                         f"The trend's format has spread beyond the city.")
    if att["tried_official_channels"]:
        headlines.append(f"{len(att['tried_official_channels'])} ask(s) say they already tried 311 or the "
                         f"community board first, so for them the video is a last resort.")
    responses = [a for a in anns if a.genre == "response"]
    if responses and service:
        rm, sm = _median([a.record.views for a in responses]), med.get("service_ask") or 0
        if sm and rm >= 1.5 * sm:
            headlines.append(f"{len(responses)} \"he fixed it\" videos have median {rm:,} views, {rm / sm:.1f}× the "
                             f"median NYC service ask ({sm:,}). Stories about fixes travel further than the asks.")
    dups = sections["echoes"]["duplicates"]
    if dups:
        headlines.append(f"{sum(d['videos'] for d in dups)} videos are near-identical scripts posted by different "
                         f"accounts ({len(dups)} group(s)). Don't count them as independent voices.")
    if named_waves:
        w = named_waves[0]
        headlines.append(f"Biggest story wave: \"{w['label']}\": {w['videos']} videos from {w['creators']} "
                         f"creators over {_span(w['span_hours'])}, {w['news_or_official']} from news/official accounts.")
    return {"tiles": tiles, "headlines": headlines}


def build_from_records(records: list[Record], source_label: str = "fixture") -> dict:
    anns = [annotate(r) for r in records]
    tones = {a.record.id: sentiment.tone(a.record.text) for a in anns}
    waves = echoes.narrative_waves(anns)
    sections: dict[str, Any] = {
        "genres": genres_section(anns),
        "themes": themes_section(anns),
        "attention": attention_section(anns),
        "echoes": {"waves": [w for w in waves if w["named"]], "loose_waves": sum(1 for w in waves if not w["named"]),
                   "same_issue": echoes.same_issue_groups(anns), "closures": echoes.closures(anns),
                   "duplicates": echoes.duplicate_scripts(anns),
                   "method": f"TF-IDF + average-linkage clustering (cosine ≥ {echoes.WAVE_THRESHOLD}); waves need "
                             f"≥{echoes.MIN_WAVE_CREATORS} creators and a shared theme. Same-issue: same primary "
                             f"theme within {echoes.SAME_ISSUE_WINDOW.days} days from 2+ creators."},
        "voices": voices_section(anns),
        "quotes": quotes_section(anns),
        "sentiment": sentiment_section(anns, tones),
    }
    sections["blind_spots"] = ome.blind_spots(anns, sections["themes"]["fit_gap"], sections["attention"],
                                              sections["themes"]["unthemed"])
    sections["engagement_plan"] = ome.engagement_plan(anns, tones, sections["echoes"]["waves"],
                                                      sections["echoes"]["closures"])
    sections["overview"] = overview_section(anns, sections)
    dated = sorted(r.posted_at for r in records if r.posted_at)
    try:
        from app.services import gemini_service

        llm = gemini_service.is_configured()
    except Exception:  # noqa: BLE001
        llm = False
    sections["meta"] = {
        "source": source_label, "records": len(records),
        "from": _iso(dated[0]) if dated else None, "to": _iso(dated[-1]) if dated else None,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "method": "rules + statistics (no LLM)", "llm_available": llm,
        "llm_note": "A Gemini key is configured: an LLM pass could re-check low-confidence genre labels and write "
                    "theme summaries. Not wired in yet." if llm else
                    "No LLM key configured. Every label is rule-based and explainable.",
        "caveats": [c.format(days=(dated[-1] - dated[0]).days + 1 if dated else 0) for c in CAVEATS], "genres": {k: v["label"] for k, v in GENRES.items()},
        "themes": {k: v["label"] for k, v in L.THEMES.items()},
    }
    return sections


def build(source: str = "auto") -> dict:
    records, label = load(source)
    mtime = CORPUS_PATH.stat().st_mtime if CORPUS_PATH.exists() else 0
    key = (label, len(records), max((r.posted_at for r in records if r.posted_at), default=None),
           sum(r.views for r in records), mtime)
    if key not in _cache:
        _cache.clear()
        _cache[key] = build_from_records(records, label)
    return _cache[key]
