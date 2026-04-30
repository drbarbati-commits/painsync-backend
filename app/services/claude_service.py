"""
AI service for PainSync — uses OpenAI-compatible API.
Default model: gemini-2.5-flash (free tier via the pre-configured base URL).
Falls back gracefully if the API key is not set.
"""
import json
import os
from typing import List, Dict, Optional
from openai import OpenAI
from app.core.config import settings

# ── Client setup ──────────────────────────────────────────────────────────────
# Use OPENAI_API_KEY env var if set, otherwise fall back to the sandbox key.
_api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
_base_url = settings.OPENAI_BASE_URL  # defaults to https://api.openai.com/v1
_model = settings.AI_MODEL            # defaults to gemini-2.5-flash

client = OpenAI(api_key=_api_key, base_url=_base_url)

# ── System prompts ────────────────────────────────────────────────────────────
SYSTEM_PROMPT_CHAT = """You are PainSync AI, an empathetic and knowledgeable chronic pain management assistant.
Your role is to help users understand their pain, provide evidence-based coping strategies, and offer emotional support.
Important guidelines:
- Be empathetic, warm, and supportive at all times
- Provide clear, medically accurate information in accessible language
- NEVER diagnose conditions or prescribe medications
- Always recommend consulting a healthcare professional for medical decisions
- Focus on pain management strategies, lifestyle adjustments, and emotional wellbeing
- If a user describes emergency symptoms (severe chest pain, difficulty breathing, sudden severe headache, etc.),
  immediately advise them to call emergency services or go to the nearest emergency room
- Keep responses concise but thorough — typically 2-4 paragraphs
"""

SYSTEM_PROMPT_TRIAGE = """You are a clinical triage assistant for a chronic pain management application.
Analyze the provided pain data and return a structured JSON triage assessment.
Your response MUST be valid JSON with exactly these fields:
{
  "urgency": "emergency" | "urgent" | "routine",
  "recommendation": "clear, actionable recommendation for the patient",
  "reasoning": "brief clinical reasoning for the urgency classification"
}
Urgency definitions:
- "emergency": Symptoms suggesting life-threatening conditions — advise calling emergency services immediately
- "urgent": Symptoms requiring same-day or next-day medical attention
- "routine": Symptoms manageable with standard care, follow-up within days to weeks
Be empathetic but clinically precise. Never diagnose. Always recommend professional consultation.
"""

SYSTEM_PROMPT_FOOD = """You are a clinical nutrition analyst for a chronic pain management app.
Analyze the provided meal description and return a structured JSON nutrition assessment.
Your response MUST be valid JSON with exactly these fields:
{
  "food_description": "comma-separated list of identified food items",
  "estimated_calories": <number or null>,
  "estimated_protein_g": <number or null>,
  "estimated_carbs_g": <number or null>,
  "estimated_fat_g": <number or null>,
  "intake_percentage": <0-100 number representing how much was consumed, null if only one photo>,
  "ai_notes": "brief clinical observations about the meal, eating ability, and any pain-relevant nutritional notes"
}
Be conservative with estimates. Note any anti-inflammatory or pro-inflammatory foods relevant to chronic pain.
If only a before-photo description is provided, set intake_percentage to null.
"""

SYSTEM_PROMPT_VIDEO = """You are a clinical pain assessment specialist analyzing patient-reported pain indicators.
Based on the provided video metadata and context, provide a structured pain assessment.
Your response MUST be valid JSON with exactly these fields:
{
  "facial_pain_score": <0.0-10.0 float or null>,
  "voice_pain_indicators": {"tone": "description", "patterns": "description"},
  "behavioral_indicators": {"movement": "description", "posture": "description"},
  "overall_pain_estimate": <0.0-10.0 float or null>,
  "ai_observations": "comprehensive clinical observations",
  "confidence_score": <0.0-1.0 float>
}
Be conservative and evidence-based. This is for documentation purposes only, not diagnosis.
"""

SYSTEM_PROMPT_SLEEP = """You are a sleep medicine specialist analyzing sleep data for a chronic pain patient.
Analyze the provided sleep log data and return structured JSON insights.
Your response MUST be valid JSON with exactly these fields:
{
  "quality_assessment": "brief assessment of sleep quality",
  "pain_sleep_correlation": "observations about pain and sleep relationship",
  "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"],
  "ai_insights": "comprehensive sleep health insights relevant to chronic pain management"
}
"""

# ── Internal helper ───────────────────────────────────────────────────────────
def _chat(system: str, user: str, max_tokens: int = 512) -> str:
    """Send a single-turn chat completion and return the text response."""
    response = client.chat.completions.create(
        model=_model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""


def _parse_json(raw: str) -> dict:
    """Strip markdown code fences and parse JSON."""
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        # parts[1] is the content between first pair of ```
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── Public API ────────────────────────────────────────────────────────────────
def chat_with_ai(messages: List[Dict], system: Optional[str] = None) -> str:
    """Multi-turn chat. messages is a list of {role, content} dicts."""
    sys_prompt = system or SYSTEM_PROMPT_CHAT
    openai_messages = [{"role": "system", "content": sys_prompt}]
    for m in messages:
        openai_messages.append({"role": m["role"], "content": m["content"]})
    response = client.chat.completions.create(
        model=_model,
        max_tokens=1024,
        messages=openai_messages,
    )
    return response.choices[0].message.content or ""


def triage_with_claude(pain_data: dict) -> dict:
    """Submit pain data for AI triage assessment. Returns parsed JSON dict."""
    prompt = (
        f"Please assess the following pain report and provide a triage recommendation:\n"
        f"Pain Level: {pain_data.get('pain_level')}/10\n"
        f"Location: {pain_data.get('pain_location')}\n"
        f"Duration: {pain_data.get('duration_hours', pain_data.get('duration_minutes', 'Not specified'))} "
        f"{'hours' if pain_data.get('duration_hours') else 'minutes'}\n"
        f"Symptoms: {', '.join(pain_data.get('symptoms', [])) or 'None specified'}\n"
        f"Additional Notes: {pain_data.get('notes') or 'None'}\n"
        f"Respond with valid JSON only."
    )
    raw = _chat(SYSTEM_PROMPT_TRIAGE, prompt, max_tokens=512)
    try:
        result = _parse_json(raw)
    except (json.JSONDecodeError, IndexError):
        result = {
            "urgency": "routine",
            "recommendation": "Please consult your healthcare provider for a proper assessment.",
            "reasoning": "AI assessment temporarily unavailable.",
        }
    result["model_used"] = _model
    return result


def analyze_food_photos(
    before_url: str,
    after_url: Optional[str] = None,
    meal_type: Optional[str] = None,
) -> dict:
    """Analyze food photos to estimate nutrition and intake percentage."""
    meal_context = f"Meal type: {meal_type}. " if meal_type else ""
    if after_url:
        prompt = (
            f"{meal_context}Two meal photos are provided:\n"
            f"BEFORE eating: {before_url}\n"
            f"AFTER eating: {after_url}\n\n"
            f"Analyze the food items, estimate nutritional content, and estimate what percentage "
            f"of the food was consumed by comparing before and after. Note any observations about "
            f"eating ability or difficulty relevant to chronic pain management. "
            f"Respond with valid JSON only."
        )
    else:
        prompt = (
            f"{meal_context}A meal photo (before eating) is provided: {before_url}\n\n"
            f"Identify the food items, estimate nutritional content, and note any anti-inflammatory "
            f"or pro-inflammatory foods relevant to chronic pain. "
            f"Set intake_percentage to null since no after photo is available. "
            f"Respond with valid JSON only."
        )
    raw = _chat(SYSTEM_PROMPT_FOOD, prompt, max_tokens=512)
    try:
        return _parse_json(raw)
    except (json.JSONDecodeError, IndexError):
        return {
            "food_description": "Analysis unavailable",
            "estimated_calories": None,
            "estimated_protein_g": None,
            "estimated_carbs_g": None,
            "estimated_fat_g": None,
            "intake_percentage": None,
            "ai_notes": raw,
        }


def analyze_pain_video_text(
    video_url: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> dict:
    """Analyze pain video context using AI. Provides structured pain assessment."""
    duration_info = f"Video duration: {duration_seconds:.1f} seconds. " if duration_seconds else ""
    url_info = f"Video reference: {video_url}. " if video_url else ""
    prompt = (
        f"{duration_info}{url_info}"
        f"Based on the available video context, provide a structured pain assessment. "
        f"This is a patient self-recorded video for chronic pain documentation. "
        f"Assess observable pain indicators including facial expressions, vocal patterns, "
        f"movement limitations, and behavioral signs of pain. "
        f"Provide a conservative, evidence-based assessment. "
        f"Respond with valid JSON only."
    )
    raw = _chat(SYSTEM_PROMPT_VIDEO, prompt, max_tokens=512)
    try:
        return _parse_json(raw)
    except (json.JSONDecodeError, IndexError):
        return {
            "facial_pain_score": None,
            "voice_pain_indicators": {"tone": "unavailable", "patterns": "unavailable"},
            "behavioral_indicators": {"movement": "unavailable", "posture": "unavailable"},
            "overall_pain_estimate": None,
            "ai_observations": raw,
            "confidence_score": 0.0,
        }


def analyze_sleep_data(sleep_data: dict) -> dict:
    """Analyze sleep log data and provide AI insights."""
    prompt = (
        f"Analyze this sleep log for a chronic pain patient:\n"
        f"Bedtime: {sleep_data.get('bedtime', 'Not recorded')}\n"
        f"Wake time: {sleep_data.get('wake_time', 'Not recorded')}\n"
        f"Duration: {sleep_data.get('duration_hours', 'Unknown')} hours\n"
        f"Quality rating: {sleep_data.get('quality_rating', 'Not rated')}/5\n"
        f"Had night pain: {sleep_data.get('had_night_pain', False)}\n"
        f"Night pain level: {sleep_data.get('night_pain_level', 'None')}\n"
        f"Disruptors: {sleep_data.get('disruptors', 'None')}\n"
        f"Notes: {sleep_data.get('notes', 'None')}\n"
        f"Respond with valid JSON only."
    )
    raw = _chat(SYSTEM_PROMPT_SLEEP, prompt, max_tokens=512)
    try:
        return _parse_json(raw)
    except (json.JSONDecodeError, IndexError):
        return {
            "quality_assessment": "Analysis unavailable",
            "pain_sleep_correlation": "Unable to assess at this time.",
            "recommendations": ["Maintain a consistent sleep schedule",
                                "Avoid screens 1 hour before bed",
                                "Consult your doctor if pain disrupts sleep regularly"],
            "ai_insights": raw,
        }
