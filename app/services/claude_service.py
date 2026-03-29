import anthropic
from typing import List, Dict
from app.core.config import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

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
- "emergency": Symptoms suggesting life-threatening conditions (severe chest pain, signs of stroke, etc.) — advise calling 911 immediately
- "urgent": Symptoms requiring same-day or next-day medical attention (severe uncontrolled pain, new neurological symptoms, etc.)
- "routine": Symptoms manageable with standard care, follow-up within days to weeks

Be empathetic but clinically precise. Never diagnose. Always recommend professional consultation.
"""


def chat_with_claude(messages: List[Dict[str, str]], user_context: str = "") -> str:
    """Send a multi-turn conversation to Claude and return the assistant response."""
    system = SYSTEM_PROMPT_CHAT
    if user_context:
        system += f"\n\nUser context: {user_context}"

    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def triage_with_claude(pain_data: dict) -> dict:
    """Submit pain data to Claude for triage assessment. Returns parsed JSON dict."""
    import json

    prompt = f"""Please assess the following pain report and provide a triage recommendation:

Pain Level: {pain_data.get('pain_level')}/10
Location: {pain_data.get('pain_location')}
Duration: {pain_data.get('duration_hours', 'Not specified')} hours
Symptoms: {', '.join(pain_data.get('symptoms', [])) or 'None specified'}
Additional Notes: {pain_data.get('notes') or 'None'}

Respond with valid JSON only."""

    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT_TRIAGE,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)
    result["model_used"] = settings.CLAUDE_MODEL
    return result
