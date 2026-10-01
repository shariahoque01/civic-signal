"""Discover public TikTok videos for the "Mamdani, fix this" corpus from hashtag pages (logged out).

    .venv/bin/python -m scripts.discover_tiktok                      # seeds + snowball, writes data/candidates_all.json
    .venv/bin/python -m scripts.discover_tiktok --tags mamdanifixthis --no-snowball
    .venv/bin/python -m scripts.discover_tiktok --max-tags 25 --max-scrolls 60 --headful

How it works: opens https://www.tiktok.com/tag/<tag> in headless Chromium, scrolls until no new videos
load, and records every video from the page's own item_list API responses (id, handle, post time,
caption, hashtags) plus any /video/ links in the DOM. "Snowball" mode then ranks hashtags that co-occur
on Mamdani-related videos and crawls the most promising ones, capped at --max-tags pages in total.
Requests are sequential with pauses between scrolls and pages. Nothing is posted, liked, or followed.

Output is merged into the existing file (discovered_via accumulates), so re-runs only add.
Requires: .venv/bin/pip install playwright && .venv/bin/python -m playwright install chromium
"""
import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SEED_TAGS = [
    "mamdanifixthis", "fixthismamdani", "mamdanifixit", "fixitmamdani", "mamdanipleasefix",
    "dearmamdani", "heymamdani", "mamdani", "zohranmamdani", "zohran", "mayormamdani",
]
# Tags too generic to be worth a crawl slot even if they co-occur a lot.
GENERIC_TAGS = {
    "fyp", "foryou", "foryoupage", "fypシ", "fypage", "viral", "trending", "tiktok", "nyc", "newyork",
    "newyorkcity", "explore", "explorepage", "capcut", "funny", "comedy", "duet", "stitch", "greenscreen",
    "fy", "parati", "xyzbca", "trend", "news", "politics", "usa", "america", "ny", "trump", "meme",
}
# Snowball only crawls tags whose name contains one of these (unless --broad). A first run without this
# rule drifted into #trump, #netanyahu, #meme, #socialism, #leftist, #nyclife: ~1,000 mostly off-topic videos.
RELEVANT_HINTS = ("mamdani", "zohran", "zorhan", "mayor", "fixthis", "311")
# Caption/hashtag text that marks a candidate as worth fetching (see is_prefilter_relevant).
CAPTION_RE = re.compile(r"mamdani|zohran|zorhan|mayor|fix|311", re.I)
DEFAULT_OUT = Path("data/candidates_all.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
VIDEO_RE = re.compile(r"tiktok\.com/@([^/]+)/video/(\d+)")


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def load_candidates(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    if isinstance(data, str):  # tolerate an accidentally double-encoded file
        data = json.loads(data)
    return {c["url"]: c for c in data}


def is_prefilter_relevant(c: dict) -> bool:
    """Worth fetching: found on a Mamdani/Zohran tag page, or caption/hashtags mention the mayor or a fix."""
    if any(re.search(r"mamdani|zohran|zorhan", v) for v in c.get("discovered_via") or []):
        return True
    if "caption" not in c and not c.get("hashtags"):
        return True  # DOM-only find, no text to judge by: fetch it
    return bool(CAPTION_RE.search((c.get("caption") or "") + " " + " ".join(c.get("hashtags") or [])))


def _is_relevant(c: dict) -> bool:
    text = (c.get("caption") or "").lower() + " " + " ".join(c.get("hashtags") or [])
    return any(h in text for h in ("mamdani", "zohran"))


def _add(found: dict[str, dict], handle: str, vid: str, tag: str, item: dict | None = None) -> None:
    url = f"https://www.tiktok.com/@{handle}/video/{vid}"
    c = found.setdefault(url, {"url": url, "platform": "tiktok", "handle": handle,
                               "posted_at": _iso(int(vid) >> 32), "discovered_via": []})
    if f"#{tag}" not in c["discovered_via"]:
        c["discovered_via"].append(f"#{tag}")
    if item:
        c["caption"] = item.get("desc") or c.get("caption") or ""
        tags = [t["hashtagName"].lower() for t in item.get("textExtra") or [] if t.get("hashtagName")]
        tags += [ch["title"].lower() for ch in item.get("challenges") or [] if ch.get("title")]
        c["hashtags"] = list(dict.fromkeys((c.get("hashtags") or []) + tags))
        if item.get("createTime"):
            c["posted_at"] = _iso(int(item["createTime"]))


async def crawl_tag(page, tag: str, found: dict[str, dict], max_scrolls: int) -> int:
    before = len(found)

    async def on_response(resp):
        if "/api/challenge/item_list" not in resp.url:
            return
        try:
            body = await resp.json()
        except Exception:
            return
        for item in body.get("itemList") or []:
            handle = (item.get("author") or {}).get("uniqueId")
            if handle and item.get("id"):
                _add(found, handle, str(item["id"]), tag, item)

    page.on("response", on_response)
    try:
        await page.goto(f"https://www.tiktok.com/tag/{tag}", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(4000)
        stalls, last = 0, -1
        for _ in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1800)
            hrefs = await page.evaluate(
                "[...document.querySelectorAll('a[href*=\"/video/\"]')].map(a => a.href.split('?')[0])")
            for h in hrefs:
                m = VIDEO_RE.search(h)
                if m:
                    _add(found, m.group(1), m.group(2), tag)
            if len(hrefs) == last:
                stalls += 1
                if stalls >= 4:
                    break
                # nudge: scroll up a bit and back down, which sometimes re-triggers the loader
                await page.evaluate("window.scrollBy(0, -1500)")
                await page.wait_for_timeout(1500)
            else:
                stalls = 0
            last = len(hrefs)
    except Exception as exc:  # timeouts, captcha pages, etc. — keep what we have
        print(f"  ! #{tag}: {exc.__class__.__name__}: {str(exc)[:120]}")
    finally:
        page.remove_listener("response", on_response)
    return len(found) - before


def next_tags(found: dict[str, dict], crawled: set[str], limit: int, broad: bool = False) -> list[str]:
    counts: Counter[str] = Counter()
    for c in found.values():
        if _is_relevant(c):
            counts.update(set(c.get("hashtags") or []))
    ranked = []
    for tag, n in counts.most_common():
        if tag in crawled or tag in GENERIC_TAGS or n < 2 or not re.fullmatch(r"[\w]+", tag):
            continue
        hinted = any(h in tag for h in RELEVANT_HINTS)
        if hinted or broad:
            ranked.append((0 if hinted else 1, -n, tag))
    return [t for _, _, t in sorted(ranked)[:limit]]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", nargs="*", default=SEED_TAGS, help="seed hashtags (no #)")
    ap.add_argument("--max-tags", type=int, default=25, help="total tag pages to crawl, seeds included")
    ap.add_argument("--max-scrolls", type=int, default=60)
    ap.add_argument("--no-snowball", action="store_true")
    ap.add_argument("--broad", action="store_true", help="snowball may crawl tags without a Mamdani/mayor hint")
    ap.add_argument("--headful", action="store_true", help="show the browser window")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    from playwright.async_api import async_playwright

    found = load_candidates(args.out)
    start = len(found)
    queue, crawled, log = list(dict.fromkeys(t.lstrip("#").lower() for t in args.tags)), set(), {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headful)
        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = await ctx.new_page()
        while queue and len(crawled) < args.max_tags:
            tag = queue.pop(0)
            crawled.add(tag)
            new = await crawl_tag(page, tag, found, args.max_scrolls)
            seen = sum(1 for c in found.values() if f"#{tag}" in c["discovered_via"])
            log[tag] = {"seen": seen, "new": new}
            print(f"#{tag:<28} seen {seen:>4}  new {new:>4}  total {len(found)}", flush=True)
            for c in found.values():
                c["prefilter_relevant"] = is_prefilter_relevant(c)
            args.out.write_text(json.dumps(sorted(found.values(), key=lambda c: c["posted_at"], reverse=True), indent=1))
            if not queue and not args.no_snowball:
                queue = next_tags(found, crawled, args.max_tags - len(crawled), args.broad)
                if queue:
                    print("  snowball ->", ", ".join(queue))
            await page.wait_for_timeout(2000)
        await browser.close()
    print(f"\n{len(found)} candidates ({len(found) - start} new) -> {args.out}")
    (args.out.with_suffix(".log.json")).write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
