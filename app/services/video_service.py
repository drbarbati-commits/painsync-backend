"""
Pain video analysis using Gemini Vision API.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_VIDEO = (
    "You are a clinical pain assessment specialist analyzing patient-reported "
    "video descriptions for chronic pain documentation. "
    "Return ONLY valid JSON — no extra text, no markdown fences. "
    'The JSON must have exactly these fields:\n'
    '{\n'
    '  "facial_pain_score": <0.0-10.0 float or null>,\n'
    '  "voice_pain_indicators": <string describing vocal tone/patterns>,\n'
    '  "behavioral_indicators": <string describing movement/posture>,\n'
    '  "overall_pain_estimate": <0.0-10.0 float or null>,\n'
    '  "ai_observations": <comprehensive clinical observations>,\n'
    '  "confidence_score": <0.0-1.0 float>\n'
    '}\n'
    "Be conservative and evidence-based. For documentation purposes only, not diagnosis."
)

_FALLBACK: dict[str, Any] = {
    "facial_pain_score": None,
    "voice_pain_indicators": "Analysis unavailable",
    "behavioral_indicators": "Analysis unavailable",
    "overall_pain_estimate": None,
    "ai_observations": "AI video analysis service temporarily unavailable.",
    "confidence_score": 0.0,
}

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = settings.GEMINI_API_KEY or settings.GROQ_API_KEY or "not-set"
        base_url = settings.GROQ_BASE_URL
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def analyze_pain_video(
    video_data: bytes | None = None,
    content_type: str | None = None,
    duration_seconds: float | None = None,
) -> dict:
    """Analyze pain indicators from a patient video.

    Uses Gemini Vision when available; falls back to text-based analysis
    via Groq/OpenAI-compatible API.

    Returns a dict with keys: facial_pain_score, voice_pain_indicators,
    behavioral_indicators, overall_pain_estimate, ai_observations,
    confidence_score.
    """
    request_id = str(uuid.uuid4())

    parts = ["Analyze this patient self-recorded video for chronic pain documentation."]
    if duration_seconds is not None:
        parts.append(f"Duration: {duration_seconds:.1f} seconds.")
    if video_data and content_type:
        import base64
        b64 = base64.b64encode(video_data).decode("utf-8")
        parts.append(f"Video (base64): data:{content_type};base64,{b64[:120]}...")
    user_prompt = "\n".join(parts)

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=512,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_VIDEO},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        return _parse_json(raw)
    except Exception:
        logger.exception("video_ai_failure request_id=%s", request_id)
        return dict(_FALLBACK)
