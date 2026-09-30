Build the Civic Signal FastAPI backend for a one-day NYC civic intelligence hackathon.

## Project Overview
Civic Signal converts public NYC social-media content (TikTok, Instagram) into structured civic observations that can be reviewed by humans and aggregated into recurring civic signals.

The MVP focuses on:
- Manual URL/file submission (not automated scraping)
- AI-powered extraction with Gemini 2.5 Flash
- Human review workflow
- Simple signal aggregation
- REST API access

## Complete Requirements

### Tech Stack
- Python 3.11+
- Framework: FastAPI 0.104.1
- Database: SQLite with SQLAlchemy ORM
- AI: Gemini 2.5 Flash API
- Video extraction: yt-dlp (supports TikTok, Instagram, MP4)
- Dependency manager: uv (NOT pip)
- Async/await support throughout

### Project Structure
Create in current directory: