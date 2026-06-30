"""
Unit tests for app.services.triage_service.

All AI calls are intercepted via mocks — no real API credits are consumed.

Coverage
--------
TestTriageWithAiSuccess        — happy-path: valid JSON, disclaimer, normalisation
TestTriageWithAiTimeout        — APITimeoutError → fallback, retry count = 2
TestTriageWithAiAPIError       — HTTP 5xx → fallback + 1 retry; 4xx → no retry
TestTriageWithAiSchemaValidation — malformed JSON, wrong urgency, missing fields
TestTriageRateLimit            — rate-limit middleware returns 429 + Retry-After
"""
from __future__ import annotations

import json
import os

import httpx
import pytest

# Env vars must be set before any app import
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used-in-tests")

from app.services.triage_service import (  # noqa: E402
    FALLBACK_RESPONSE,
    triage_with_ai,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_PAIN_DATA: dict = {
    "pain_level": 7,
    "pain_location": "chest",
    "duration_hours": 2.0,
    "symptoms": ["tightness", "shortness_of_breath"],
    "notes": "Onset during rest — synthetic test data",
}

_VALID_AI_JSON: dict = {
    "urgency": "urgent",
    "recommendation": "Seek professional attention today.",
    "reasoning": "Chest pain with respiratory symptoms warrants prompt evaluation.",
}


def _mock_client(mocker, content: str):
    """Patch _get_client to return a MagicMock that yields *content* from chat.completions.create."""
    mock = mocker.MagicMock()
    mock.chat.completions.create.return_value.choices[0].message.content = content
    mocker.patch("app.services.triage_service._get_client", return_value=mock)
    return mock


# ── Success scenarios ─────────────────────────────────────────────────────────


class TestTriageWithAiSuccess:
    """Happy-path tests for triage_with_ai."""

    def test_returns_valid_schema(self, mocker) -> None:
        """A well-formed AI response is parsed, validated, and returned."""
        _mock_client(mocker, json.dumps(_VALID_AI_JSON))
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["urgency"] == "urgent"
        assert isinstance(result["recommendation"], str)
        assert len(result["recommendation"]) > 0
        assert isinstance(result["reasoning"], str)
        assert "model_used" in result

    def test_wellness_disclaimer_appended_to_recommendation(self, mocker) -> None:
        """The wellness disclaimer is always appended to the recommendation."""
        _mock_client(mocker, json.dumps(_VALID_AI_JSON))
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert "healthcare professional" in result["recommendation"].lower()

    def test_urgency_is_normalised_to_lowercase(self, mocker) -> None:
        """Urgency values returned in mixed case are lowercased."""
        _mock_client(mocker, json.dumps({**_VALID_AI_JSON, "urgency": "ROUTINE"}))
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["urgency"] == "routine"

    def test_markdown_fenced_json_is_parsed(self, mocker) -> None:
        """AI responses wrapped in ```json … ``` code fences are handled."""
        fenced = f"```json\n{json.dumps(_VALID_AI_JSON)}\n```"
        _mock_client(mocker, fenced)
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["urgency"] == "urgent"

    def test_model_used_reflects_settings(self, mocker) -> None:
        """model_used is populated from settings.GROQ_MODEL, not from the AI response."""
        _mock_client(mocker, json.dumps(_VALID_AI_JSON))
        result = triage_with_ai(_VALID_PAIN_DATA)
        from app.core.config import settings
        assert result["model_used"] == settings.GROQ_MODEL

    def test_all_three_urgency_values_are_accepted(self, mocker) -> None:
        """emergency, urgent, and routine are all valid urgency values."""
        for urgency in ("emergency", "urgent", "routine"):
            _mock_client(mocker, json.dumps({**_VALID_AI_JSON, "urgency": urgency}))
            result = triage_with_ai(_VALID_PAIN_DATA)
            assert result["urgency"] == urgency


# ── Timeout scenarios ─────────────────────────────────────────────────────────


class TestTriageWithAiTimeout:
    """APITimeoutError must trigger fallback; the function must never raise."""

    def test_timeout_returns_fallback_response(self, mocker) -> None:
        """APITimeoutError produces the standard fallback dict."""
        from openai import APITimeoutError

        mock = mocker.MagicMock()
        mock.chat.completions.create.side_effect = APITimeoutError(
            request=mocker.MagicMock(spec=httpx.Request)
        )
        mocker.patch("app.services.triage_service._get_client", return_value=mock)

        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["model_used"] == "fallback"
        assert result["urgency"] == "routine"

    def test_timeout_never_raises(self, mocker) -> None:
        """The function returns a dict even when every attempt times out."""
        from openai import APITimeoutError

        mock = mocker.MagicMock()
        mock.chat.completions.create.side_effect = APITimeoutError(
            request=mocker.MagicMock(spec=httpx.Request)
        )
        mocker.patch("app.services.triage_service._get_client", return_value=mock)

        result = triage_with_ai(_VALID_PAIN_DATA)
        assert isinstance(result, dict)

    def test_timeout_retries_exactly_once(self, mocker) -> None:
        """APITimeoutError causes exactly two call attempts (_MAX_RETRIES + 1 = 2)."""
        from openai import APITimeoutError

        mock = mocker.MagicMock()
        mock.chat.completions.create.side_effect = APITimeoutError(
            request=mocker.MagicMock(spec=httpx.Request)
        )
        mocker.patch("app.services.triage_service._get_client", return_value=mock)

        triage_with_ai(_VALID_PAIN_DATA)
        assert mock.chat.completions.create.call_count == 2

    def test_fallback_contains_wellness_disclaimer(self, mocker) -> None:
        """Even the fallback response includes the wellness disclaimer."""
        from openai import APITimeoutError

        mock = mocker.MagicMock()
        mock.chat.completions.create.side_effect = APITimeoutError(
            request=mocker.MagicMock(spec=httpx.Request)
        )
        mocker.patch("app.services.triage_service._get_client", return_value=mock)

        result = triage_with_ai(_VALID_PAIN_DATA)
        assert "healthcare professional" in result["recommendation"].lower()


# ── API error scenarios ───────────────────────────────────────────────────────


class TestTriageWithAiAPIError:
    """HTTP error responses from the AI provider."""

    def _make_status_error(self, mocker, status_code: int, message: str = "Error"):
        from openai import APIStatusError

        # Do not use spec=httpx.Response — APIStatusError.__init__ also accesses
        # response.request and response.headers which spec would restrict.
        mock_resp = mocker.MagicMock()
        mock_resp.status_code = status_code
        mock_resp.headers = {}
        mock_resp.request = mocker.MagicMock(spec=httpx.Request)
        return APIStatusError(message=message, response=mock_resp, body=None)

    def test_server_error_returns_fallback(self, mocker) -> None:
        """HTTP 500 from the AI provider triggers the fallback response."""
        mock = mocker.MagicMock()
        mock.chat.completions.create.side_effect = self._make_status_error(
            mocker, 500, "Internal Server Error"
        )
        mocker.patch("app.services.triage_service._get_client", return_value=mock)
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["model_used"] == "fallback"

    def test_server_error_retries_once(self, mocker) -> None:
        """HTTP 5xx errors are retried once before falling back."""
        mock = mocker.MagicMock()
        mock.chat.completions.create.side_effect = self._make_status_error(
            mocker, 503, "Service Unavailable"
        )
        mocker.patch("app.services.triage_service._get_client", return_value=mock)
        triage_with_ai(_VALID_PAIN_DATA)
        assert mock.chat.completions.create.call_count == 2

    def test_client_error_is_not_retried(self, mocker) -> None:
        """HTTP 4xx errors are not retried (same request will always fail)."""
        mock = mocker.MagicMock()
        mock.chat.completions.create.side_effect = self._make_status_error(
            mocker, 400, "Bad Request"
        )
        mocker.patch("app.services.triage_service._get_client", return_value=mock)
        triage_with_ai(_VALID_PAIN_DATA)
        assert mock.chat.completions.create.call_count == 1

    def test_server_error_never_raises(self, mocker) -> None:
        """The function never propagates API exceptions to the caller."""
        mock = mocker.MagicMock()
        mock.chat.completions.create.side_effect = self._make_status_error(
            mocker, 500
        )
        mocker.patch("app.services.triage_service._get_client", return_value=mock)
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert isinstance(result, dict)


# ── Schema validation failure scenarios ───────────────────────────────────────


class TestTriageWithAiSchemaValidation:
    """Malformed or schema-mismatched AI responses must trigger the fallback."""

    def test_malformed_json_returns_fallback(self, mocker) -> None:
        """Non-JSON text from the AI triggers the fallback response."""
        _mock_client(mocker, "Sorry, I cannot help with that.")
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["model_used"] == "fallback"

    def test_malformed_json_not_retried(self, mocker) -> None:
        """Schema errors are not retried (same prompt → same bad output)."""
        mock = _mock_client(mocker, "this is definitely not JSON")
        triage_with_ai(_VALID_PAIN_DATA)
        assert mock.chat.completions.create.call_count == 1

    def test_invalid_urgency_value_returns_fallback(self, mocker) -> None:
        """An urgency value outside {emergency, urgent, routine} triggers fallback."""
        bad = {"urgency": "critical", "recommendation": "See a doctor.", "reasoning": "High pain."}
        _mock_client(mocker, json.dumps(bad))
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["model_used"] == "fallback"

    def test_missing_recommendation_returns_fallback(self, mocker) -> None:
        """A response missing 'recommendation' triggers the fallback."""
        bad = {"urgency": "routine", "reasoning": "Low pain."}
        _mock_client(mocker, json.dumps(bad))
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["model_used"] == "fallback"

    def test_missing_reasoning_returns_fallback(self, mocker) -> None:
        """A response missing 'reasoning' triggers the fallback."""
        bad = {"urgency": "routine", "recommendation": "Rest and monitor."}
        _mock_client(mocker, json.dumps(bad))
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["model_used"] == "fallback"

    def test_empty_string_response_returns_fallback(self, mocker) -> None:
        """An empty AI response triggers the fallback."""
        _mock_client(mocker, "")
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["model_used"] == "fallback"

    def test_non_dict_json_returns_fallback(self, mocker) -> None:
        """A JSON array (not an object) triggers the fallback."""
        _mock_client(mocker, json.dumps(["emergency", "see a doctor"]))
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["model_used"] == "fallback"

    def test_empty_recommendation_string_returns_fallback(self, mocker) -> None:
        """An empty-string recommendation is rejected."""
        bad = {"urgency": "routine", "recommendation": "   ", "reasoning": "Low pain."}
        _mock_client(mocker, json.dumps(bad))
        result = triage_with_ai(_VALID_PAIN_DATA)
        assert result["model_used"] == "fallback"


# ── Rate limiting ─────────────────────────────────────────────────────────────


class TestTriageRateLimit:
    """The TriageRateLimitMiddleware enforces 10 requests/min per token."""

    def test_eleventh_request_returns_429(self, client, auth_headers, mock_claude) -> None:
        """The 11th POST /triage/ from the same user within 60 s returns HTTP 429."""
        for _ in range(10):
            resp = client.post("/triage/", headers=auth_headers, json={
                "pain_level": 5,
                "pain_location": "lower_back",
            })
            assert resp.status_code == 201

        resp = client.post("/triage/", headers=auth_headers, json={
            "pain_level": 5,
            "pain_location": "lower_back",
        })
        assert resp.status_code == 429

    def test_429_includes_retry_after_header(self, client, auth_headers, mock_claude) -> None:
        """The 429 response includes a Retry-After header."""
        for _ in range(10):
            client.post("/triage/", headers=auth_headers, json={
                "pain_level": 5,
                "pain_location": "lower_back",
            })

        resp = client.post("/triage/", headers=auth_headers, json={
            "pain_level": 5,
            "pain_location": "lower_back",
        })
        assert resp.status_code == 429
        assert "retry-after" in {k.lower() for k in resp.headers}

    def test_unauthenticated_request_not_blocked_by_rate_limit(
        self, client
    ) -> None:
        """Requests without a token pass through to the auth layer (returns 401, not 429)."""
        resp = client.post("/triage/", json={"pain_level": 5, "pain_location": "back"})
        assert resp.status_code == 401

    def test_get_request_not_rate_limited(self, client, auth_headers) -> None:
        """GET /triage/ is never subject to rate limiting."""
        for _ in range(15):
            resp = client.get("/triage/", headers=auth_headers)
            assert resp.status_code == 200
