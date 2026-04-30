"""
Tests for /triage/* endpoints.

All AI calls are intercepted by the `mock_claude` fixture so that no real API
credits are consumed and results are fully deterministic.

Coverage:
  POST /triage/ — valid request with mock, exact response schema, urgency enum,
                  auth enforcement, 503 on AI timeout, validation errors
  GET  /triage/ — listing, isolation, auth enforcement

GDPR note: all symptom/location data uses synthetic, non-identifying values.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

_VALID_PAYLOAD: dict = {
    "pain_level": 7,
    "pain_location": "chest",
    "duration_hours": 2.0,
    "symptoms": ["tightness", "shortness_of_breath"],
    "notes": "Onset during rest — synthetic test data",
}

_EXPECTED_SCHEMA_KEYS = {"id", "urgency", "recommendation", "reasoning", "model_used", "created_at"}


# ── POST /triage/ ─────────────────────────────────────────────────────────────

class TestCreateTriage:
    """POST /triage/ (AI call mocked)"""

    def test_valid_request_returns_201(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """A valid triage request returns HTTP 201 Created."""
        resp = client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)
        assert resp.status_code == 201

    def test_response_contains_exact_schema(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """Response body includes exactly the documented fields."""
        resp = client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)
        assert resp.status_code == 201
        missing = _EXPECTED_SCHEMA_KEYS - set(resp.json().keys())
        assert not missing, f"Missing response fields: {missing}"

    def test_urgency_is_valid_enum_value(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """The `urgency` field must be one of: emergency | urgent | routine."""
        resp = client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)
        assert resp.status_code == 201
        assert resp.json()["urgency"] in ("emergency", "urgent", "routine")

    def test_recommendation_is_non_empty_string(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """The `recommendation` field must be a non-empty string."""
        resp = client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)
        assert resp.status_code == 201
        assert isinstance(resp.json()["recommendation"], str)
        assert len(resp.json()["recommendation"]) > 0

    def test_reasoning_is_non_empty_string(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """The `reasoning` field must be a non-empty string."""
        resp = client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)
        assert resp.status_code == 201
        assert isinstance(resp.json()["reasoning"], str)
        assert len(resp.json()["reasoning"]) > 0

    def test_model_used_reflects_mock_name(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """model_used echoes the mock-model identifier from the fixture."""
        resp = client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)
        assert resp.status_code == 201
        assert resp.json()["model_used"] == "mock-model"

    def test_unauthenticated_request_returns_401(
        self,
        client: TestClient,
        mock_claude,
    ) -> None:
        """A request without a bearer token returns HTTP 401."""
        resp = client.post("/triage/", json=_VALID_PAYLOAD)
        assert resp.status_code == 401

    def test_ai_timeout_returns_503(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mocker,
    ) -> None:
        """When the AI service raises an exception the endpoint returns HTTP 503."""
        mocker.patch(
            "app.api.routes.triage.triage_with_ai",
            side_effect=TimeoutError("AI service timed out"),
        )
        resp = client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)
        assert resp.status_code == 503

    def test_ai_runtime_error_returns_503(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mocker,
    ) -> None:
        """Any unhandled exception from the AI layer maps to HTTP 503."""
        mocker.patch(
            "app.api.routes.triage.triage_with_ai",
            side_effect=RuntimeError("Connection refused"),
        )
        resp = client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)
        assert resp.status_code == 503

    def test_missing_pain_level_returns_422(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """Omitting the required `pain_level` field returns HTTP 422."""
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "pain_level"}
        resp = client.post("/triage/", headers=auth_headers, json=payload)
        assert resp.status_code == 422

    def test_missing_pain_location_returns_422(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """Omitting the required `pain_location` field returns HTTP 422."""
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "pain_location"}
        resp = client.post("/triage/", headers=auth_headers, json=payload)
        assert resp.status_code == 422

    def test_pain_level_out_of_range_returns_422(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """pain_level values outside [1, 10] are rejected."""
        resp = client.post(
            "/triage/",
            headers=auth_headers,
            json={**_VALID_PAYLOAD, "pain_level": 0},
        )
        assert resp.status_code == 422


# ── GET /triage/ ─────────────────────────────────────────────────────────────

class TestListTriageAssessments:
    """GET /triage/"""

    def test_returns_200_with_list(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Authenticated GET /triage/ returns HTTP 200 and a list."""
        resp = client.get("/triage/", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_empty_list_for_new_user(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """A user with no assessments receives an empty list."""
        resp = client.get("/triage/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_created_assessment_appears_in_list(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """A newly created triage assessment is visible in the list."""
        client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)
        resp = client.get("/triage/", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_unauthenticated_list_returns_401(self, client: TestClient) -> None:
        """Listing assessments without a token returns HTTP 401."""
        resp = client.get("/triage/")
        assert resp.status_code == 401

    def test_user_sees_only_own_assessments(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_claude,
    ) -> None:
        """User A's triage list does not include User B's assessments."""
        # User A creates an assessment
        client.post("/triage/", headers=auth_headers, json=_VALID_PAYLOAD)

        # Register User B and verify their list is empty
        client.post(
            "/auth/register",
            json={
                "name": "Other",
                "email": "other_triage@example.com",
                "password": "OtherPass123!",
            },
        )
        b_login = client.post(
            "/auth/login",
            json={"email": "other_triage@example.com", "password": "OtherPass123!"},
        )
        b_headers = {"Authorization": f"Bearer {b_login.json()['access_token']}"}
        resp = client.get("/triage/", headers=b_headers)
        assert resp.status_code == 200
        assert resp.json() == []
