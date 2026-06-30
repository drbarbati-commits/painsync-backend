"""Tests for food_service.py AI analysis."""
from __future__ import annotations

import json
import types

import pytest

from app.services.food_service import analyze_food_image


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


class TestAnalyzeFoodImage:
    def test_returns_expected_keys_on_success(self, mocker):
        mock_response = {
            "food_description": "grilled chicken, rice, broccoli",
            "estimated_calories": 550,
            "estimated_protein_g": 45,
            "estimated_carbs_g": 60,
            "estimated_fat_g": 12,
        }
        mocker.patch(
            "app.services.food_service._get_client",
            return_value=_mock_openai(json.dumps(mock_response)),
        )
        result = analyze_food_image(b"fake-image-data", "image/jpeg", meal_type="lunch")
        assert result["food_description"] == "grilled chicken, rice, broccoli"
        assert result["estimated_calories"] == 550

    def test_fallback_on_api_failure(self, mocker):
        mocker.patch(
            "app.services.food_service._get_client",
            side_effect=RuntimeError("API down"),
        )
        result = analyze_food_image(b"fake-data", "image/jpeg")
        assert result["food_description"] == "Analysis unavailable"
        assert result["estimated_calories"] is None

    def test_accepts_meal_type_and_notes(self, mocker):
        mocker.patch(
            "app.services.food_service._get_client",
            return_value=_mock_openai(
                '{"food_description":"salad","estimated_calories":300,"estimated_protein_g":10,"estimated_carbs_g":20,"estimated_fat_g":15,"ai_notes":"Fresh greens."}'
            ),
        )
        result = analyze_food_image(b"data", "image/png", meal_type="dinner", notes="no dressing")
        assert result["food_description"] == "salad"

    def test_handles_empty_image_data(self, mocker):
        mocker.patch(
            "app.services.food_service._get_client",
            return_value=_mock_openai(
                '{"food_description":"","estimated_calories":null,"estimated_protein_g":null,"estimated_carbs_g":null,"estimated_fat_g":null,"ai_notes":"No food detected."}'
            ),
        )
        result = analyze_food_image(b"", "image/jpeg")
        assert result["food_description"] == ""
