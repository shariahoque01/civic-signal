# Civic Signal

Turn public NYC social-media posts into structured civic observations that staff can review and act on.

> **AI suggests, staff decide.**

---

## What It Does

Civic Signal monitors public TikTok and Instagram content for civic issues — broken infrastructure, sanitation problems, unsafe conditions — and converts them into structured observations alongside manual video submissions.

```
Social media discovery + manual uploads
              ↓
        AI processing
              ↓
   Structured civic observation
              ↓
      Human review & report
              ↓
     Recurring civic signals
              ↓
        REST API access
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI |
| Database | SQLite + SQLAlchemy |
| AI | Google Gemini 2.5 Flash |
| Video extraction | yt-dlp |
| Frontend | Vanilla JS / HTML / CSS |

---

## Getting Started

```bash
git clone https://github.com/your-org/civic-signal.git
cd civic-signal/backend

uv sync

cp .env.example .env
# Add your GEMINI_API_KEY to .env

uv run uvicorn app.main:app --reload
```

App: [http://localhost:8000/ui/](http://localhost:8000/ui/)

---

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/process` | Submit a URL or video file |
| `GET` | `/api/observations` | List observations |
| `PATCH` | `/api/observations/{id}` | Update (human review) |
| `GET` | `/api/signals` | Recurring civic signals |
| `GET` | `/api/cases` | Full cases with source context |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `DATABASE_URL` | No | Defaults to `sqlite:///./database.db` |
| `ENVIRONMENT` | No | `development` or `production` |
