"""Gemini 2.5 Flash integration. The model never invents data: unknowns come back null with low confidence."""
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import types

from app.config import get_settings
from app.utils.constants import (
    AGENCIES, BOROUGHS, DEFAULT_LANGUAGE, FALLBACK_CONFIDENCE, OBSERVATION_TYPES,
    TOPIC_AGENCY_MAP, TOPICS, URGENCIES,
)

logger = logging.getLogger(__name__)

NO_SPEECH_MARKER = "[NO_SPEECH]"
TRANSIENT_CODES = (429, 500, 503)
RETRY_ATTEMPTS = 4


class GeminiError(RuntimeError):
    pass


def is_configured() -> bool:
    key = get_settings().gemini_api_key
    return bool(key) and not key.startswith("your-")


def _client() -> genai.Client:
    key = get_settings().gemini_api_key
    if not key or key.startswith("your-"):
        raise GeminiError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=key)


def _clamp(value: Any, default: float = FALLBACK_CONFIDENCE) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _parse_json(text: str) -> dict[str, Any]:
    """Parse model output, tolerating code fences or surrounding prose."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise GeminiError("Model returned non-JSON output")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise GeminiError("Model returned malformed JSON") from exc
    if not isinstance(data, dict):
        raise GeminiError("Model returned unexpected JSON shape")
    return data


async def _generate(contents: Any, *, json_mode: bool = False) -> str:
    client = _client()
    config = types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json" if json_mode else None,
    )
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = await client.aio.models.generate_content(
                model=get_settings().gemini_model, contents=contents, config=config
            )
            break
        except Exception as exc:  # SDK raises a variety of API/network errors
            transient = getattr(exc, "code", None) in TRANSIENT_CODES
            if transient and attempt < RETRY_ATTEMPTS:
                logger.warning("Gemini busy (attempt %d/%d), retrying", attempt, RETRY_ATTEMPTS)
                await asyncio.sleep(2 ** attempt)
                continue
            logger.error("Gemini call failed: %s", exc)
            raise GeminiError(f"Gemini API error: {exc}") from exc
    if not resp.text:
        raise GeminiError("Gemini returned an empty response")
    return resp.text


EXTRACTION_PROMPT = f"""You convert public social-media content about New York City into ONE structured civic observation.

Rules:
- Use ONLY what is in the content. Never invent locations, agencies, or details. If unknown, use null and a LOW confidence (0.3-0.5 or lower).
- "evidence.quote" must be a verbatim quote from the content (empty string if none).
- Reply with a single JSON object, no prose, with exactly these keys:
  type: one of {list(OBSERVATION_TYPES)}
  topic: one of {list(TOPICS)}
  summary: 2-3 sentence English summary
  location_description: street/intersection/area or null
  borough: one of {list(BOROUGHS)} or null
  neighborhood: string or null
  location_confidence: 0-1
  agency_candidates: list of {{"name": one of {list(AGENCIES)}, "confidence": 0-1}}
  urgency: one of {list(URGENCIES)} or null
  language: ISO 639-1 code of the original content
  confidence: 0-1 overall extraction confidence
  evidence: {{"quote": "..."}}
"""


def normalize_observation(raw: dict[str, Any], default_language: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    """Coerce model output into valid enum values; unknown values degrade to 'other'/None."""
    topic = raw.get("topic") if raw.get("topic") in TOPICS else "other"
    obs_type = raw.get("type") if raw.get("type") in OBSERVATION_TYPES else "other"
    borough = raw.get("borough") if raw.get("borough") in BOROUGHS else None
    urgency = raw.get("urgency") if raw.get("urgency") in URGENCIES else None
    location_desc = raw.get("location_description") or None

    agencies: list[dict[str, Any]] = []
    for cand in raw.get("agency_candidates") or []:
        if isinstance(cand, dict) and cand.get("name") in AGENCIES:
            agencies.append({"name": cand["name"], "confidence": _clamp(cand.get("confidence"))})
    if not agencies:
        agencies = [{"name": TOPIC_AGENCY_MAP[topic], "confidence": FALLBACK_CONFIDENCE}]
    agencies.sort(key=lambda a: a["confidence"], reverse=True)

    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
    return {
        "type": obs_type,
        "topic": topic,
        "summary": str(raw.get("summary") or "No summary could be extracted.").strip(),
        "location_description": location_desc,
        "borough": borough,
        "neighborhood": raw.get("neighborhood") or None,
        # No stated location => no location confidence.
        "location_confidence": _clamp(raw.get("location_confidence")) if (location_desc or borough) else 0.0,
        "agency_candidates": agencies,
        "urgency": urgency,
        "language": str(raw.get("language") or default_language)[:8],
        "confidence": _clamp(raw.get("confidence")),
        "evidence": {"quote": str(evidence.get("quote") or "")},
    }


async def extract_observation(content: str, language: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    prompt = f"{EXTRACTION_PROMPT}\nDetected language hint: {language}\n\nCONTENT:\n{content}"
    text = await _generate(prompt, json_mode=True)
    result = normalize_observation(_parse_json(text), language)
    logger.info("Extracted observation topic=%s type=%s conf=%.2f", result["topic"], result["type"], result["confidence"])
    return result


async def classify_language(content: str) -> str:
    text = await _generate(
        "Return only the ISO 639-1 language code (e.g. en, es, zh) of the dominant language in this text:\n\n"
        + content[:2000]
    )
    code = text.strip().lower()[:8]
    return code if re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,4})?", code) else DEFAULT_LANGUAGE


async def translate_content(content: str, target_language: str = "en") -> str:
    return (await _generate(f"Translate the following text to {target_language}. Return only the translation:\n\n{content}")).strip()


VIDEO_TRANSCRIBE_PROMPT = (
    "Transcribe all spoken words and any on-screen text in this video, verbatim, in the original language. "
    "Also note briefly any visible street signs or landmarks. Do not guess."
)
SPEECH_ONLY_PROMPT = (
    "Transcribe all spoken words in this media verbatim, in the original language. "
    f"If there is no intelligible speech (silence, music only), reply exactly {NO_SPEECH_MARKER}. Do not guess or summarise."
)


async def transcribe_video(file_path: Path, prompt: str = VIDEO_TRANSCRIBE_PROMPT) -> str:
    """Transcribe a local media file via the Gemini Files API."""
    client = _client()
    try:
        uploaded = await client.aio.files.upload(file=str(file_path))
        for _ in range(60):  # wait for server-side processing
            if uploaded.state and uploaded.state.name != "PROCESSING":
                break
            await asyncio.sleep(2)
            uploaded = await client.aio.files.get(name=uploaded.name)
        if uploaded.state and uploaded.state.name == "FAILED":
            raise GeminiError("Gemini failed to process the video")
        return await _generate([uploaded, prompt])
    except GeminiError:
        raise
    except Exception as exc:
        logger.error("Video transcription failed: %s", exc)
        raise GeminiError(f"Video transcription failed: {exc}") from exc
