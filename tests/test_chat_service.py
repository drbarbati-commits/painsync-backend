"""Tests for chat_service.py context assembly and streaming."""
from __future__ import annotations

import types
from unittest.mock import AsyncMock

import pytest

from app.services.chat_service import (
    assemble_context,
    generate_stream,
    _summarize_pain_logs,
    _summarize_food_logs,
    _summarize_water_logs,
    _summarize_sleep_logs,
)


class TestSummarizePainLogs:
    def test_averages_pain_levels(self):
        logs = [_make_pain_log(7), _make_pain_log(5), _make_pain_log(3)]
        result = _summarize_pain_logs(logs)
        assert "3 entries" in result
        assert "5.0/10" in result

    def test_single_entry(self):
        logs = [_make_pain_log(8)]
        result = _summarize_pain_logs(logs)
        assert "1 entries" in result


class TestSummarizeFoodLogs:
    def test_averages_calories(self):
        logs = [_make_food_log(500), _make_food_log(300)]
        result = _summarize_food_logs(logs)
        assert "2 meals" in result
        assert "400" in result


class TestSummarizeWaterLogs:
    def test_sums_ml(self):
        logs = [_make_water_log(500), _make_water_log(750)]
        result = _summarize_water_logs(logs)
        assert "1250" in result
        assert "2 entries" in result


class TestSummarizeSleepLogs:
    def test_averages_duration_and_quality(self):
        logs = [_make_sleep_log(7.0, 4), _make_sleep_log(8.0, 3)]
        result = _summarize_sleep_logs(logs)
        assert "7.5h" in result
        assert "3.5/5" in result


class TestAssembleContext:
    @pytest.mark.asyncio
    async def test_includes_user_profile(self, mocker):
        user = types.SimpleNamespace(
            id=1, name="Alice", age=30, gender="female", medical_history="Asthma"
        )
        db = AsyncMock()
        db.execute.return_value = _async_result([])

        context = await assemble_context(user, db, days=7)
        assert "Alice" in context
        assert "30" in context
        assert "Asthma" in context

    @pytest.mark.asyncio
    async def test_includes_no_data_message_when_empty(self, mocker):
        user = types.SimpleNamespace(
            id=2, name="Bob", age=None, gender=None, medical_history=None
        )
        db = AsyncMock()
        db.execute.return_value = _async_result([])

        context = await assemble_context(user, db, days=7)
        assert "No recent pain logs" in context
        assert "No recent food logs" in context
        assert "Bob" in context

    @pytest.mark.asyncio
    async def test_streaming_generator(self, mocker):
        mocker.patch(
            "app.services.chat_service._get_client",
            return_value=_mock_streaming_client(["Hello", " ", "world"]),
        )
        messages = [{"role": "user", "content": "Hi"}]
        chunks = []
        async for chunk in generate_stream(messages, system="You are a helpful assistant."):
            chunks.append(chunk)
        assert "".join(chunks) == "Hello world"

    @pytest.mark.asyncio
    async def test_streaming_handles_empty_chunks(self, mocker):
        mocker.patch(
            "app.services.chat_service._get_client",
            return_value=_mock_streaming_client(["", None, "final"]),
        )
        chunks = []
        async for chunk in generate_stream([{"role": "user", "content": "Hi"}], system="Be helpful."):
            chunks.append(chunk)
        assert "".join(chunks) == "final"


def _make_pain_log(level):
    return types.SimpleNamespace(pain_level=level, pain_location="back")


def _make_food_log(cal):
    return types.SimpleNamespace(estimated_calories=cal)


def _make_water_log(ml):
    return types.SimpleNamespace(amount_ml=ml)


def _make_sleep_log(duration, quality):
    return types.SimpleNamespace(duration_hours=duration, quality_rating=quality)


def _async_result(items):
    class FakeScalars:
        def all(self):
            return items

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    return FakeResult()


def _mock_streaming_client(chunks):
    class MockDelta:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, delta):
            self.delta = delta

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(MockDelta(content))]

    def _stream_gen():
        for c in chunks:
            if c is not None:
                yield MockChunk(c)

    class MockCompletions:
        @staticmethod
        def create(**kwargs):
            return _stream_gen()

    class MockChat:
        completions = MockCompletions()

    class MockClient:
        chat = MockChat()

    return MockClient()
