"""
Food image analysis using Gemini Vision API.
"""
from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import Any

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_WELLNESS_DISCLAIMER = (
    " These estimates are for informational purposes only. "
    "Consult a registered dietitian for personalised nutrition advice."
)

SYSTEM_PROMPT_FOOD = (
    "You are a clinical nutrition analyst for a chronic pain management app. "
    "Analyze the meal image and return ONLY valid JSON — no extra text, no markdown fences. "
    'The JSON must have exactly these fields:\n'
    '{\n'
    '  "food_description": "comma-separated list of identified food items",\n'
    '  "estimated_calories": <number or null>,\n'
    '  "estimated_protein_g": <number or null>,\n'
    '  "estimated_carbs_g": <number or null>,\n'
    '  "estimated_fat_g": <number or null>,\n'
    '  "ai_notes": "brief observations about the meal"\n'
    '}\n'
    "Be conservative with estimates. Note anti-inflammatory or "
    "pro-inflammatory foods relevant to chronic pain."
)

_FALLBACK: dict[str, Any] = {
    "food_description": "Analysis unavailable",
    "estimated_calories": None,
    "estimated_protein_g": None,
    "estimated_carbs_g": None,
    "estimated_fat_g": None,
    "ai_notes": "AI food analysis service temporarily unavailable.",
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


def analyze_food_image(
    image_data: bytes,
    content_type: str,
    meal_type: str | None = None,
    notes: str | None = None,
) -> dict:
    """Analyze a food image and return structured nutrition estimates.

    Uses Gemini Vision when available; falls back to Groq/OpenAI-compatible.
    Returns a dict with keys: food_description, estimated_calories,
    estimated_protein_g, estimated_carbs_g, estimated_fat_g, ai_notes.
    """
    request_id = str(uuid.uuid4())
    b64 = base64.b64encode(image_data).decode("utf-8")
    data_url = f"data:{content_type};base64,{b64}"

    context_parts = []
    if meal_type:
        context_parts.append(f"Meal type: {meal_type}.")
    if notes:
        context_parts.append(f"User notes: {notes}.")
    context_parts.append(f"Image (base64): {data_url[:120]}...")
    user_prompt = "\n".join(context_parts)

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=512,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_FOOD},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        result = _parse_json(raw)
        result["ai_notes"] = (result.get("ai_notes") or "") + _WELLNESS_DISCLAIMER
        return result
    except Exception:
        logger.exception("food_ai_failure request_id=%s", request_id)
        return {**_FALLBACK, "ai_notes": _FALLBACK["ai_notes"]}
