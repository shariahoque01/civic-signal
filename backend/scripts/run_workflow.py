"""Ingest candidates into the DB: every fetched video is stored with its transcript and a relevance
label; fix requests also get an Observation and, when actionable, a 311 draft.

    .venv/bin/python -m scripts.run_workflow data/candidates_all.json          # all ages (corpus)
    .venv/bin/python -m scripts.run_workflow data/candidates_all.json --window 5
    .venv/bin/python -m scripts.run_workflow https://www.tiktok.com/@user/video/123 ...

Requests are sequential with --delay seconds between fetches (default 1.0) to stay polite.
"""
import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from app.database import SessionLocal, init_db
from app.services import workflow


def _candidates(args: list[str], include_all: bool = False) -> dict[str, list[str]]:
    """url -> discovered_via, from JSON candidate files, text files of URLs, or bare URLs."""
    out: dict[str, list[str]] = {}
    for arg in args:
        path = Path(arg)
        if path.suffix == ".json" and path.is_file():
            data = json.loads(path.read_text())
            if isinstance(data, str):
                data = json.loads(data)
            # discover_tiktok marks off-topic finds (from generic tags, no mayor/fix text) prefilter_relevant=false
            items = [(c["url"], c.get("discovered_via") or []) for c in data
                     if include_all or c.get("prefilter_relevant", True)]
        elif path.is_file():
            items = [(line.strip(), ["manual"]) for line in path.read_text().splitlines() if line.strip()]
        else:
            items = [(arg, ["manual"])]
        for url, via in items:
            url = url.split("?")[0]
            out[url] = list(dict.fromkeys(out.get(url, []) + via))
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*", default=["data/candidates_all.json"])
    ap.add_argument("--window", type=int, default=None, help="only ingest posts from the last N days")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--all", action="store_true", help="also fetch candidates marked prefilter_relevant=false")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    counts: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    try:
        for url, via in _candidates(args.inputs, args.all).items():
            r = await workflow.process_url(db, url, args.window, discovered_via=via)
            counts[r["status"]] += 1
            if r.get("relevance"):
                labels[r["relevance"]] += 1
            if r.get("service_request_id"):
                counts["311_drafts"] += 1
            extra = r.get("reason") if r["status"] != "processed" else (
                f"{r['type']}/{r['topic']}" + (" -> 311 draft" if r.get("service_request_id") else ""))
            print(f"{r['status']:>9}  {url.split('/@')[-1][:45]:45}  {r.get('relevance', ''):13} {extra}", flush=True)
            if r["status"] != "skipped":
                await asyncio.sleep(args.delay)
    finally:
        db.close()
    print("\n", dict(counts), dict(labels))


if __name__ == "__main__":
    asyncio.run(main())
