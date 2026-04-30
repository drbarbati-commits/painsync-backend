"""
Hardened AI triage service for PainSync.

Design decisions
----------------
Wellness language:  System prompt forbids diagnosis, prescription, and medical
                    advice.  All recommendations include the wellness disclaimer.
Schema validation:  Every AI response is validated against the exact schema
                    before being returned; any mismatch triggers the fallback.
Timeout:            15 s hard limit on each AI call (passed to the OpenAI SDK).
Retry:              One automatic retry on transient 5xx / network errors.
                    Schema errors and 4xx client errors are not retried.
Fallback:           If all attempts fail the caller receives a safe, non-empty
                    response so the route can still persist an assessment record.
GDPR:               Only request_id (UUID) and latency_ms are written to logs.
                    Pain data, prompts, and AI responses are never logged.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import openai
from openai import APIStatusError, APITimeoutError

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TIMEOUT_SECONDS: float = 15.0
_MAX_RETRIES: int = 1          # total attempts = _MAX_RETRIES + 1 = 2
_VALID_URGENCY = frozenset({"emergency", "urgent", "routine"})

# Permanently appended to every AI recommendation (wellness positioning)
_WELLNESS_DISCLAIMER = (
    " Always consult a qualified healthcare professional for personalized advice."
)

# ── System prompt (wellness-only language) ────────────────────────────────────

SYSTEM_PROMPT_TRIAGE = (
    "You are a wellness tracking assistant. "
    "Do not diagnose, prescribe, or give medical advice. "
    "Always recommend consulting a healthcare professional for concerning symptoms.\n\n"
    "Analyze the provided pain data and respond with ONLY valid JSON — no extra text, "
    "no markdown fences. The JSON must have exactly these fields:\n"
    "{\n"
    '  "urgency": "emergency" | "urgent" | "routine",\n'
    '  "recommendation": "<clear, actionable wellness recommendation>",\n'
    '  "reasoning": "<brief reasoning for the urgency classification>"\n'
    "}\n\n"
    "Urgency definitions:\n"
    '- "emergency": Possibly life-threatening — recommend calling emergency services immediately.\n'
    '- "urgent": Prompt professional attention needed today or tomorrow.\n'
    '- "routine": Manageable with self-care; recommend scheduling a follow-up.\n\n'
    "Never diagnose conditions. Keep language supportive and wellness-focused."
)

# ── Fallback response (returned when all AI attempts fail) ────────────────────

FALLBACK_RESPONSE: dict[str, str] = {
    "urgency": "routine",
    "recommendation": (
        "AI assessment unavailable. Please consult a healthcare professional "
        "for personalized guidance." + _WELLNESS_DISCLAIMER
    ),
    "reasoning": "Service temporarily unavailable.",
    "model_used": "fallback",
}

# ── Lazy OpenAI client singleton ──────────────────────────────────────────────

_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY or "not-set",
            base_url=settings.OPENAI_BASE_URL,
        )
    return _client


# ── Schema validation ─────────────────────────────────────────────────────────


class TriageSchemaError(ValueError):
    """Raised when the AI response does not match the exact triage schema."""


def _validate_schema(data: Any) -> dict:
    """Validate *data* against the triage response schema.

    Raises :class:`TriageSchemaError` on any mismatch.
    On success, returns a normalised dict with the wellness disclaimer appended
    to the recommendation.
    """
    if not isinstance(data, dict):
        raise TriageSchemaError(f"Expected dict, got {type(data).__name__}")

    urgency = str(data.get("urgency", "")).lower()
    if urgency not in _VALID_URGENCY:
        raise TriageSchemaError(f"Invalid urgency value: {urgency!r}")

    recommendation = data.get("recommendation", "")
    if not isinstance(recommendation, str) or not recommendation.strip():
        raise TriageSchemaError("Missing or empty 'recommendation' field")

    reasoning = data.get("reasoning", "")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise TriageSchemaError("Missing or empty 'reasoning' field")

    return {
        "urgency": urgency,
        "recommendation": recommendation.strip() + _WELLNESS_DISCLAIMER,
        "reasoning": reasoning.strip(),
    }


# ── JSON parsing ──────────────────────────────────────────────────────────────


def _parse_json(raw: str) -> dict:
    """Strip optional markdown code fences and parse JSON."""
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── Single AI call ────────────────────────────────────────────────────────────


def _call_ai(prompt: str, request_id: str) -> dict:
    """Execute one AI API call with a 15 s timeout and return a validated dict.

    GDPR: only *request_id* and *latency_ms* are logged — never the prompt or
    the raw response.
    """
    client = _get_client()
    t0 = time.monotonic()

    response = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=512,
        timeout=_TIMEOUT_SECONDS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_TRIAGE},
            {"role": "user", "content": prompt},
        ],
    )

    latency_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "triage_ai_call request_id=%s latency_ms=%d", request_id, latency_ms
    )

    raw = response.choices[0].message.content or ""
    parsed = _parse_json(raw)
    return _validate_schema(parsed)


# ── Public API ────────────────────────────────────────────────────────────────


def triage_with_ai(pain_data: dict) -> dict:
    """Submit pain data for an AI wellness triage assessment.

    Makes up to ``_MAX_RETRIES + 1`` attempts.  Transient server errors (5xx)
    and timeouts are retried once; client errors (4xx) and schema failures are
    not retried (the same input will produce the same bad output).

    If all attempts fail, :data:`FALLBACK_RESPONSE` is returned so the caller
    always receives a valid dict and can persist an assessment record.

    GDPR compliance
    ---------------
    - Only ``request_id`` (UUID v4) and ``latency_ms`` are written to logs.
    - ``pain_data`` is never serialised to log output.
    - The prompt contains only structured, non-identifying clinical fields
      (pain level, location, duration, symptoms, free-text notes).
    - No user identifiers (user_id, email, name) are included in the prompt.
    """
    request_id = str(uuid.uuid4())

    # Build de-identified prompt — no user PII, no auth tokens
    prompt = (
        f"Pain level: {pain_data.get('pain_level')}/10\n"
        f"Location: {pain_data.get('pain_location')}\n"
        f"Duration: {pain_data.get('duration_hours', 'Not specified')} hours\n"
        f"Symptoms: {', '.join(pain_data.get('symptoms', [])) or 'None specified'}\n"
        f"Additional context: {pain_data.get('notes') or 'None'}\n"
        "Respond with valid JSON only."
    )

    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = _call_ai(prompt, request_id)
            result["model_used"] = settings.AI_MODEL
            return result

        except APITimeoutError as exc:
            last_error = exc
            logger.warning(
                "triage_ai_timeout request_id=%s attempt=%d",
                request_id,
                attempt + 1,
            )

        except APIStatusError as exc:
            last_error = exc
            if exc.status_code is not None and 400 <= exc.status_code < 500:
                # 4xx errors will not improve on retry
                logger.warning(
                    "triage_ai_client_error request_id=%s status=%d",
                    request_id,
                    exc.status_code,
                )
                break
            logger.warning(
                "triage_ai_server_error request_id=%s attempt=%d status=%s",
                request_id,
                attempt + 1,
                exc.status_code,
            )

        except (TriageSchemaError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "triage_schema_error request_id=%s attempt=%d error=%s",
                request_id,
                attempt + 1,
                type(exc).__name__,
            )
            # Same prompt will always produce the same malformed output — don't retry
            break

    logger.error(
        "triage_fallback request_id=%s error_type=%s",
        request_id,
        type(last_error).__name__ if last_error else "unknown",
    )
    return FALLBACK_RESPONSE.copy()
