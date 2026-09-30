# Civic Signal Backend — Changes & Overview

Notes for building the frontend against the API as it currently stands.

## What we changed along the way
- **Model:** switched from `gemini-2.5-flash` (retired for new users) to `gemini-3.8-flash`. It's set with `GEMINI_MODEL` in `backend/.env`.
- **Retries:** Gemini calls now retry 429/500/503 errors up to 4 times with backoff.
- **Audio transcription:** for TikTok/Instagram URLs, the backend downloads the audio to a temp folder, Gemini transcribes the speech, and the temp files are deleted. It's skipped when the video has real subtitles or runs over 300 seconds. If it fails, extraction continues with the caption only.
- **Fewer Gemini calls:** removed the separate language-detection call. A request now makes 2 calls, or 1 when subtitles exist.

## Running it
```
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
```
Base URL: `http://127.0.0.1:8000`. Swagger docs at `/docs`.

**CORS:** only `http://localhost:3000` and `http://localhost:5173` are allowed, with GET, POST and PATCH. If your frontend runs on another port, add it to `CORS_ORIGINS` in `app/utils/constants.py`.

## Endpoints
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health` | none | `{status, timestamp, version}` |
| POST | `/api/process` | `{url, platform, caption?}` or `{platform:"upload", file_path}` | 201, one Observation |
| GET | `/api/observations` | `status, borough, topic, type, limit (default 100, max 500), offset` | `{total, count, observations: [...]}`, newest first |
| GET | `/api/observations/{id}` | none | one Observation, or 404 |
| PATCH | `/api/observations/{id}` | any of: `status, final_agency, final_priority, reviewer_notes, type, topic, borough, urgency, location_description` | the updated Observation |
| GET | `/api/signals` | none | `{total, signals: [...]}` |
| POST | `/api/signals/aggregate` | none | `{message, signals_created, signals_updated, groups_found}` |

## Observation shape
```json
{
  "id": "obs_…", "source_id": "src_…",
  "type": "issue", "topic": "rats",
  "summary": "…",
  "location": { "description": "…", "borough": "Bronx", "neighborhood": null,
                "confidence": 0.5, "needs_review": false },
  "agency_candidates": [{ "name": "NYC DOHMH", "confidence": 0.8 }],
  "urgency": "medium", "language": "en", "confidence": 0.8,
  "evidence": { "quote": "…" },
  "status": "new", "reviewed_at": null, "reviewer_notes": null,
  "final_agency": null, "final_priority": null,
  "created_at": "2026-09-30T20:43:59Z"
}
```
- **AI vs. staff fields:** everything except `status`, `reviewer_notes`, `final_*` and `reviewed_at` is the AI draft. Those five are set by staff, matching the purple/green split in the design.
- **Location flag:** `location.needs_review` is true when location confidence is below 0.5. Use it for the low-confidence badge.
- **`reviewed_at`:** set automatically whenever a PATCH changes something.

A **Signal** has `id, title, topic, borough, agency_candidates, observation_ids, observation_count, unique_source_count, trend, confidence, created_at`. `trend` is always null for now.

## Allowed values
PATCH and the list filters reject anything else with a 422.
- **platform:** `tiktok`, `instagram`, `upload`
- **type:** `issue`, `request`, `idea`, `praise`, `information`, `other`
- **topic:** `streetlights`, `transportation`, `trash`, `rats`, `parks`, `sidewalks`, `roads`, `public_transit`, `housing`, `public_safety`, `water`, `noise`, `construction`, `accessibility`, `public_facilities`, `other`
- **borough:** `Manhattan`, `Brooklyn`, `Queens`, `Bronx`, `Staten Island`
- **status:** `new`, `reviewed`, `rejected`
- **urgency / final_priority:** `low`, `medium`, `high`. The design uses P1–P4, so map those onto these values or ask to have the backend changed to match.
- **agencies:** `NYC DOT`, `NYC DSNY`, `NYC Parks`, `NYC DEP`, `NYC HPD`, `NYPD`, `NYC DOB`, `NYC DOHMH`, `MTA`, `NYC 311`

## Errors
Errors come back as `{"error": "message"}`. Validation errors (422) also include a `details` list.
- **400:** a bad URL for the platform.
- **404:** the ID wasn't found.
- **500:** extraction failed. This includes Gemini quota and "high demand" errors, and the message says which.

## What to design around
- **Slow requests:** `/api/process` takes about 10–40 seconds, and longer when retries kick in. Show a loading state and don't auto-retry on a 500, because each attempt uses Gemini quota.
- **No browser upload:** there's no file-upload endpoint yet. An upload only works if the file is already in `backend/uploads/`. If the intake screen needs a file picker, a multipart upload endpoint would need to be added.
- **Aggregation:** signals only appear after calling `POST /api/signals/aggregate`. It needs 2 or more **reviewed** observations with the same topic and borough.
- **Root URL:** `/` returns 404, which is expected.

## Bug found while testing: TikTok extraction needs `curl_cffi`
Posting a real TikTok URL failed with `[TikTok] Unexpected response from webpage request` — yt-dlp's TikTok extractor now has to solve an anti-bot challenge, which requires browser-TLS "impersonation," and the dependency for that (`curl_cffi`) wasn't installed. Fix: `uv pip install "curl_cffi>=0.5.10"` in the venv. This should get added as a real dependency in `pyproject.toml` (`yt-dlp[curl-cffi]` or a plain `curl_cffi>=0.5.10` entry) so a fresh `uv sync` isn't missing it. After installing it and restarting uvicorn, the curated TikTok link processed fine (201, ~35s) and matched the Observation shape documented above exactly — seeded into `backend/database.db`.

## Frontend (this session)
Built in `frontend/` — plain HTML/CSS/JS, no build step, no framework. Visual design (CSS vars, class names, purple/dashed = AI vs. green = staff) is carried over unchanged from `civic-signal.html`.

- `index.html` — markup for the three screens (Intake / Case review / Inbox), same section-toggle pattern as the design concept.
- `styles.css` — the design concept's CSS, verbatim.
- `api.js` — the **only** place that talks to the network. A `MOCK_MODE` flag at the top switches every call between local mock data and the real endpoints above; a full request/response doc comment sits above the `api` object. Methods: `processVideo`, `getCases`, `getCase`, `saveCase`.
- `app.js` — nav, rendering, and wiring the three screens to `api.js`.

Decisions baked in, in case the contract shifts again:
- **File upload** is mock-only for now. With `MOCK_MODE: false`, the upload button is disabled (there's no real upload endpoint yet — see "No browser upload" above); only the link path hits `/api/process` for real.
- **Priority** is shown as High/Medium/Low directly (not P1–P4), matching `urgency`/`final_priority`'s enum 1:1 — no translation layer to keep in sync.
- **Inbox and Case review both call the real `getCases`/`getCase`/`saveCase`** when `MOCK_MODE` is off, not just Intake — one flag governs all four methods uniformly.
- The backend doesn't return video metadata (creator handle, platform, views/shares, post date) — Case review shows these as UI-only "display" fields that are simply blank when data comes from the real API, and are never sent back in a PATCH.

Verified end-to-end with a headless-browser pass through Intake → loading → Case review → Inbox → row click → priority/status change → save → error path, with console errors checked at each step.
