"""Tests for video_service.py AI analysis."""
from __future__ import annotations

import json
import types

from app.services.video_service import analyze_pain_video


def _mock_openai(json_str: str):
    class MockChoice:
        def __init__(self):
            self.message = types.SimpleNamespace(content=json_str)

    class MockResponse:
        def __init__(self):
            self.choices = [MockChoice()]

    class MockCompletions:
        @staticmethod
        def create(**kwargs):
            return MockResponse()

    class MockChat:
        completions = MockCompletions()

    class MockClient:
        chat = MockChat()

    return MockClient()


class TestAnalyzePainVideo:
    def test_returns_expected_keys_on_success(self, mocker):
        mock_response = {
            "facial_pain_score": 6.5,
            "voice_pain_indicators": "Tense, strained vocal quality",
            "behavioral_indicators": "Guarded movement, favoring left side",
            "overall_pain_estimate": 6.0,
            "ai_observations": "Patient displays moderate pain indicators",
            "confidence_score": 0.75,
        }
        mocker.patch(
            "app.services.video_service._get_client",
            return_value=_mock_openai(json.dumps(mock_response)),
        )
        result = analyze_pain_video(
            video_data=b"fake-video-data",
            content_type="video/mp4",
            duration_seconds=30.0,
        )
        assert result["facial_pain_score"] == 6.5
        assert result["confidence_score"] == 0.75
        assert "movement" in result["behavioral_indicators"].lower()

    def test_fallback_on_api_failure(self, mocker):
        mocker.patch(
            "app.services.video_service._get_client",
            side_effect=RuntimeError("API down"),
        )
        result = analyze_pain_video()
        assert result["facial_pain_score"] is None
        assert result["confidence_score"] == 0.0

    def test_handles_null_duration(self, mocker):
        mock_response = {
            "facial_pain_score": None,
            "voice_pain_indicators": "No audio available",
            "behavioral_indicators": "Limited movement visible",
            "overall_pain_estimate": 4.0,
            "ai_observations": "Partial assessment",
            "confidence_score": 0.5,
        }
        mocker.patch(
            "app.services.video_service._get_client",
            return_value=_mock_openai(json.dumps(mock_response)),
        )
        result = analyze_pain_video(duration_seconds=None)
        assert result["overall_pain_estimate"] == 4.0
        assert result["facial_pain_score"] is None

    def test_handles_malformed_json(self, mocker):
        mocker.patch(
            "app.services.video_service._get_client",
            return_value=_mock_openai("not valid json"),
        )
        result = analyze_pain_video(b"data", "video/mp4")
        assert result["facial_pain_score"] is None
        assert result["confidence_score"] == 0.0
