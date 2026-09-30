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
