"""Build the offline analysis corpus from candidate TikTok URLs.

    .venv/bin/python -m app.services.analysis.build_corpus [--refresh]

Fetches each public post sequentially (~1s spacing) with tiktok_service.fetch_post and caches
results to data/analysis_corpus.json. Already-cached URLs are skipped unless --refresh.
Real public data only: failures are recorded as errors, never filled in.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.services import tiktok_service

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CORPUS_PATH = DATA_DIR / "analysis_corpus.json"
CANDIDATE_FILES = ["candidates_tiktok.json", "mamdanifixthis_candidates.json"]


def _load_json(path: Path):
    data = json.loads(path.read_text())
    return json.loads(data) if isinstance(data, str) else data  # some files are double-encoded


def load_candidates() -> list[dict]:
    seen: dict[str, dict] = {}
    for name in CANDIDATE_FILES:
        path = DATA_DIR / name
        if not path.exists():
            continue
        for c in _load_json(path):
            url = c.get("url")
            if not url:
                continue
            if url in seen:
                seen[url]["discovered_via"] = sorted(set(seen[url].get("discovered_via", [])) | set(c.get("discovered_via", [])))
            else:
                seen[url] = dict(c)
    return list(seen.values())


def _record(url: str, cand: dict, post: tiktok_service.TikTokPost) -> dict:
    m = post.meta
    return {
        "url": url,
        "platform": "tiktok",
        "handle": m.creator_handle or cand.get("handle"),
        "posted_at": m.posted_at.isoformat() + "Z" if m.posted_at else cand.get("posted_at"),
        "caption": m.caption,
        "hashtags": m.hashtags,
        "mentions": m.mentions,
        "speech": post.speech,
        "speech_language": post.speech_language,
        "location_tag": post.location_tag,
        "on_screen_text": post.on_screen_text,
        "views": m.view_count,
        "likes": m.like_count,
        "comments": post.comment_count,
        "shares": post.share_count,
        "transcript": tiktok_service.as_transcript(post),
        "discovered_via": cand.get("discovered_via", []),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def build(refresh: bool = False, delay: float = 1.0) -> dict:
    existing = {}
    if CORPUS_PATH.exists() and not refresh:
        existing = {r["url"]: r for r in json.loads(CORPUS_PATH.read_text()).get("records", [])}
    errors: dict[str, str] = {}
    cands = load_candidates()
    for i, cand in enumerate(cands):
        url = cand["url"]
        if url in existing and "error" not in existing[url]:
            continue
        try:
            post = await tiktok_service.fetch_post(url)
            existing[url] = _record(url, cand, post)
            print(f"[{i+1}/{len(cands)}] ok  {url}  speech={len(post.speech)}ch", flush=True)
        except Exception as exc:  # noqa: BLE001 - record and move on
            errors[url] = str(exc)
            print(f"[{i+1}/{len(cands)}] ERR {url}: {exc}", flush=True)
        await asyncio.sleep(delay)
    out = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": "Public TikTok pages via tiktok_service.fetch_post (no login). Handles only.",
        "candidate_count": len(cands),
        "records": sorted(existing.values(), key=lambda r: r.get("posted_at") or ""),
        "errors": errors,
    }
    CORPUS_PATH.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    result = asyncio.run(build(refresh="--refresh" in sys.argv))
    print(f"records={len(result['records'])} errors={len(result['errors'])}")
