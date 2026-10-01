# Civic Signal Backend

FastAPI service that turns public TikTok/Instagram posts into structured civic observations
(Gemini 2.5 Flash), supports human review, and aggregates reviewed items into signals.

## Run
```
cd backend
uv sync --extra dev
cp .env.example .env      # add GEMINI_API_KEY (https://ai.google.dev)
uv run uvicorn app.main:app --reload --port 8000
```
Docs: http://localhost:8000/docs · Tests: `uv run pytest`

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| POST | /api/process | URL or uploaded file → observation (201) |
| GET | /api/observations | List; filters: status, borough, topic, type, limit, offset |
| GET | /api/observations/{id} | One observation |
| PATCH | /api/observations/{id} | Human review edits |
| GET | /api/signals | Aggregated signals |
| POST | /api/signals/aggregate | Group reviewed observations by (topic, borough), 2+ each |
| GET | /health | Health check |

Local video files: put them in `backend/uploads/` and send `{"platform":"upload","file_path":"clip.mp4"}`.

## Building the TikTok corpus ("Mamdani, fix this")
Every fetched video is stored as a `Source` with its transcript (caption, location tag, on-screen text,
TikTok ASR captions) and a `relevance` label: `fix_request` (tags the mayor and asks for a fix, about NYC),
`outside_nyc` (a fix request about another city or country), `mayor_related`, or `unrelated`. Only fix requests become Observations and, when actionable, 311 drafts
(what `/api/cases` shows). Old posts are kept; filter by `sources.posted_at` at query time.

```
.venv/bin/pip install playwright && .venv/bin/python -m playwright install chromium   # once
.venv/bin/python -m scripts.migrate_db              # add new Source columns to an existing database.db
.venv/bin/python -m scripts.discover_tiktok         # crawl seed tag pages + snowball (<=25 pages) -> data/candidates_all.json
.venv/bin/python -m scripts.run_workflow data/candidates_all.json            # ingest all ages
.venv/bin/python -m scripts.run_workflow data/candidates_all.json --window 5 # or only the last 5 days
.venv/bin/python -m scripts.relabel [--dry-run]     # re-apply relevance rules to stored rows, no fetching
```
`run_workflow` skips candidates marked `prefilter_relevant: false` (found only on generic tags, with no
mayor/fix text in the caption); pass `--all` to fetch them too. Snowball only follows tags whose name
contains mamdani/zohran/mayor/fixthis/311 unless `--broad` is given.
Discovery is logged-out and sequential; each tag page yields roughly 150 videos before TikTok stops
serving more. Options: `--tags a b c`, `--no-snowball`, `--max-tags`, `--max-scrolls`, `--headful`.
Re-runs merge into the candidate file and skip URLs already in the DB (adding any new `discovered_via`).
Per-tag counts are written to `data/candidates_all.log.json`.

## Frontend and public snapshot
- Local app: start the server (above), then open http://localhost:8000/ (redirects to `/ui/`, which serves `../frontend`).
  Pages: Overview, 311 work orders, Sentiment, What 311 misses, Where to show up, Videos, Add.
- Public site: Vercel can't run this backend as-is (writable SQLite, live TikTok fetching, headless browser),
  so we publish a read-only snapshot of the frontend plus exported data:
  ```
  .venv/bin/python -m scripts.export_static   # writes ../dist (frontend + data/*.json)
  cd ../dist && vercel deploy --prod
  ```
  In the snapshot, api.js reads `data/*.json` and editing/adding videos is disabled.
