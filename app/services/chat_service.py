"""
Chat service — context assembly and streaming response generation.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, List

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.models.pain_log import PainLog
from app.models.wellness import FoodLog, WaterLog, SleepLog

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = settings.GROQ_API_KEY or "not-set"
        _client = AsyncOpenAI(api_key=api_key, base_url=settings.GROQ_BASE_URL)
    return _client


_SYSTEM_BASE = (
    "You are PainSync AI, an empathetic chronic pain management assistant. "
    "Be warm, supportive, and medically accurate. "
    "Never diagnose or prescribe. "
    "Always recommend consulting a healthcare professional for medical decisions. "
    "If the user describes emergency symptoms, advise calling emergency services immediately."
)

_WELLNESS_FOOTER = (
    "\n\nRemember: I am an AI assistant, not a doctor. "
    "Always consult a qualified healthcare professional for personalised medical advice."
)


async def assemble_context(
    user: User,
    db: AsyncSession,
    days: int = 7,
) -> str:
    """Build a personalised system prompt with user profile and recent health data.

    Fetches medical profile, pain logs, food logs, water logs, and sleep logs
    for the last *days* days.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    profile_parts = [f"Patient name: {user.name}"]
    if user.age:
        profile_parts.append(f"Age: {user.age}")
    if user.gender:
        profile_parts.append(f"Gender: {user.gender}")
    if user.medical_history:
        profile_parts.append(f"Medical history: {user.medical_history}")
    profile = ". ".join(profile_parts) + "."

    pain_result = await db.execute(
        select(PainLog)
        .where(PainLog.user_id == user.id, PainLog.created_at >= cutoff)
        .order_by(PainLog.created_at.desc())
    )
    pain_logs = pain_result.scalars().all()
    pain_summary = _summarize_pain_logs(pain_logs) if pain_logs else "No recent pain logs."

    food_result = await db.execute(
        select(FoodLog)
        .where(FoodLog.user_id == user.id, FoodLog.created_at >= cutoff)
        .order_by(FoodLog.created_at.desc())
    )
    food_logs = food_result.scalars().all()
    food_summary = _summarize_food_logs(food_logs) if food_logs else "No recent food logs."

    water_result = await db.execute(
        select(WaterLog)
        .where(WaterLog.user_id == user.id, WaterLog.created_at >= cutoff)
        .order_by(WaterLog.created_at.desc())
    )
    water_logs = water_result.scalars().all()
    water_summary = _summarize_water_logs(water_logs) if water_logs else "No recent water logs."

    sleep_result = await db.execute(
        select(SleepLog)
        .where(SleepLog.user_id == user.id, SleepLog.created_at >= cutoff)
        .order_by(SleepLog.created_at.desc())
    )
    sleep_logs = sleep_result.scalars().all()
    sleep_summary = _summarize_sleep_logs(sleep_logs) if sleep_logs else "No recent sleep logs."

    context = (
        f"{_SYSTEM_BASE}\n\n"
        f"Patient context:\n{profile}\n\n"
        f"Recent data (last {days} days):\n"
        f"--- Pain ---\n{pain_summary}\n\n"
        f"--- Food ---\n{food_summary}\n\n"
        f"--- Hydration ---\n{water_summary}\n\n"
        f"--- Sleep ---\n{sleep_summary}\n\n"
        "Use this context to provide personalised, empathetic support. "
        "Keep responses concise but thorough (2-4 paragraphs typically)."
        f"{_WELLNESS_FOOTER}"
    )
    return context


def _summarize_pain_logs(logs: list) -> str:
    levels = [log.pain_level for log in logs if log.pain_level is not None]
    avg = sum(levels) / len(levels) if levels else 0
    return f"{len(logs)} entries recorded. Average pain level: {avg:.1f}/10. Latest: {logs[0].pain_level}/10 at {logs[0].pain_location or 'unspecified location'}."


def _summarize_food_logs(logs: list) -> str:
    meals = len(logs)
    cals = [log.estimated_calories for log in logs if log.estimated_calories is not None]
    avg_cal = sum(cals) / len(cals) if cals else 0
    return f"{meals} meals logged. Average estimated calories: {avg_cal:.0f}."


def _summarize_water_logs(logs: list) -> str:
    total = sum(log.amount_ml for log in logs if log.amount_ml is not None)
    return f"Total water intake: {total:.0f} ml over {len(logs)} entries."


def _summarize_sleep_logs(logs: list) -> str:
    durations = [log.duration_hours for log in logs if log.duration_hours is not None]
    avg = sum(durations) / len(durations) if durations else 0
    ratings = [log.quality_rating for log in logs if log.quality_rating is not None]
    avg_q = sum(ratings) / len(ratings) if ratings else 0
    return f"{len(logs)} nights logged. Average duration: {avg:.1f}h. Average quality: {avg_q:.1f}/5."


async def generate_stream(
    messages: List[dict],
    system: str,
) -> AsyncGenerator[str, None]:
    """Generate a streaming chat completion.

    Yields content chunks as they arrive from the API.
    Uses AsyncOpenAI so iteration does not block the event loop.
    """
    client = _get_client()
    openai_messages = [{"role": "system", "content": system}]
    for m in messages:
        openai_messages.append({"role": m["role"], "content": m["content"]})

    stream = await client.chat.completions.create(
        model=settings.GROQ_MODEL,
        max_tokens=1024,
        messages=openai_messages,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        content = delta.content if delta else None
        if content:
            yield content
