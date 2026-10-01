"""Recompute Source.relevance from stored fields after the rules change. No TikTok requests.

    .venv/bin/python -m scripts.relabel            # apply
    .venv/bin/python -m scripts.relabel --dry-run  # just show changes

Rows that stop being fix requests lose their Observation / 311 draft (unless a draft was already
filed or approved, which is kept and reported). Rows that become fix requests are extracted and drafted
(Gemini if configured, else keywords), exactly as at ingest.
"""
import argparse
import asyncio
from collections import Counter

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Source
from app.services import workflow
from app.services.video_service import PostMetadata
from app.utils.constants import RELEVANCE_FIX


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    init_db()
    db = SessionLocal()
    moves: Counter[str] = Counter()
    try:
        for src in db.scalars(select(Source).where(Source.platform == "tiktok")).all():
            meta = PostMetadata(caption=src.caption or "", hashtags=src.hashtags or [], mentions=src.mentions or [])
            new = workflow.relevance(meta, src.transcript or "", src.location_tag)
            if new == src.relevance:
                continue
            moves[f"{src.relevance} -> {new}"] += 1
            print(f"{src.relevance:>13} -> {new:<13} @{src.creator_handle}  {(src.caption or '')[:70]!r}")
            if args.dry_run:
                continue
            src.relevance = new
            if new != RELEVANCE_FIX:
                for obs in list(src.observations):
                    sr = obs.service_request
                    if sr is not None and sr.status in ("approved", "filed"):
                        print(f"    kept {sr.status} 311 draft {sr.id}")
                        continue
                    if sr is not None:
                        db.delete(sr)
                    db.delete(obs)
                db.commit()
            elif not src.observations:
                await workflow.extract_and_draft(db, src)
            else:
                db.commit()
    finally:
        db.close()
    print("\n", dict(moves) or "no changes")


if __name__ == "__main__":
    asyncio.run(main())
