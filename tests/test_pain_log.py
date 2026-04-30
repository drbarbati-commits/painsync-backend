"""
Tests for /pain-log/* endpoints.

Coverage:
  POST   /pain-log/       — valid schema, missing required fields, auth enforcement
  GET    /pain-log/       — pagination, empty state, auth enforcement
  GET    /pain-log/{id}   — found, not found, cross-user isolation
  DELETE /pain-log/{id}   — success, not found, data removed

GDPR note: all test pain data uses synthetic values — no real health information.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

_VALID_PAYLOAD: dict = {
    "pain_level": 6,
    "pain_location": "lower_back",
    "symptoms": ["stiffness", "aching"],
    "notes": "Worse in the morning — synthetic test data",
}


# ── POST /pain-log/ ───────────────────────────────────────────────────────────

class TestCreatePainLog:
    """POST /pain-log/"""

    def test_valid_entry_returns_201_with_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A complete, valid payload creates an entry and returns HTTP 201."""
        resp = client.post("/pain-log/", headers=auth_headers, json=_VALID_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["pain_level"] == 6
        assert body["pain_location"] == "lower_back"
        assert "id" in body
        assert "timestamp" in body
        assert "created_at" in body

    def test_unauthenticated_request_returns_401(self, client: TestClient) -> None:
        """Submitting a pain log without a token returns HTTP 401."""
        resp = client.post("/pain-log/", json=_VALID_PAYLOAD)
        assert resp.status_code == 401

    def test_pain_level_too_high_returns_422(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """pain_level > 10 violates the schema constraint (ge=1, le=10)."""
        resp = client.post(
            "/pain-log/",
            headers=auth_headers,
            json={**_VALID_PAYLOAD, "pain_level": 11},
        )
        assert resp.status_code == 422

    def test_pain_level_too_low_returns_422(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """pain_level < 1 violates the schema constraint."""
        resp = client.post(
            "/pain-log/",
            headers=auth_headers,
            json={**_VALID_PAYLOAD, "pain_level": 0},
        )
        assert resp.status_code == 422

    def test_missing_pain_location_returns_422(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """The required `pain_location` field must be present."""
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "pain_location"}
        resp = client.post("/pain-log/", headers=auth_headers, json=payload)
        assert resp.status_code == 422

    def test_missing_pain_level_returns_422(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """The required `pain_level` field must be present."""
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "pain_level"}
        resp = client.post("/pain-log/", headers=auth_headers, json=payload)
        assert resp.status_code == 422

    def test_optional_fields_are_accepted(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A minimal payload (only required fields) is accepted."""
        resp = client.post(
            "/pain-log/",
            headers=auth_headers,
            json={"pain_level": 3, "pain_location": "neck"},
        )
        assert resp.status_code == 201

    def test_symptoms_stored_and_returned(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """The `symptoms` list is persisted and returned in the response."""
        resp = client.post(
            "/pain-log/",
            headers=auth_headers,
            json={**_VALID_PAYLOAD, "symptoms": ["burning", "tingling"]},
        )
        assert resp.status_code == 201
        assert resp.json()["symptoms"] == ["burning", "tingling"]


# ── GET /pain-log/ ─────────────────────────────────────────────────────────────

class TestListPainLogs:
    """GET /pain-log/"""

    def _create(
        self,
        client: TestClient,
        headers: dict[str, str],
        pain_level: int = 5,
    ) -> dict:
        resp = client.post(
            "/pain-log/",
            headers=headers,
            json={**_VALID_PAYLOAD, "pain_level": pain_level},
        )
        assert resp.status_code == 201
        return resp.json()

    def test_list_returns_paginated_schema(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Response always includes items, total, page, page_size, total_pages."""
        self._create(client, auth_headers)
        resp = client.get("/pain-log/", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        for key in ("items", "total", "page", "page_size", "total_pages"):
            assert key in body, f"Missing key: {key}"

    def test_empty_list_for_new_user(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A new user's pain log list is empty."""
        resp = client.get("/pain-log/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    def test_page_size_limits_returned_items(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """page_size=2 returns at most 2 items per page."""
        for i in range(3):
            self._create(client, auth_headers, pain_level=i + 1)
        resp = client.get("/pain-log/?page=1&page_size=2", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 3
        assert body["total_pages"] == 2

    def test_second_page_returns_remaining_items(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """The second page of a 3-item list returns 1 item."""
        for i in range(3):
            self._create(client, auth_headers, pain_level=i + 1)
        resp = client.get("/pain-log/?page=2&page_size=2", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    def test_unauthenticated_request_returns_401(self, client: TestClient) -> None:
        """Listing pain logs without a token returns HTTP 401."""
        resp = client.get("/pain-log/")
        assert resp.status_code == 401

    def test_user_sees_only_own_entries(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A user's list contains only their own entries."""
        self._create(client, auth_headers)

        # Second user
        client.post(
            "/auth/register",
            json={
                "name": "Other",
                "email": "other_list@example.com",
                "password": "OtherPass123!",
            },
        )
        other_login = client.post(
            "/auth/login",
            json={"email": "other_list@example.com", "password": "OtherPass123!"},
        )
        other_headers = {
            "Authorization": f"Bearer {other_login.json()['access_token']}"
        }
        resp = client.get("/pain-log/", headers=other_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ── GET /pain-log/{id} ────────────────────────────────────────────────────────

class TestGetPainLog:
    """GET /pain-log/{id}"""

    def test_fetch_existing_entry_by_id(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Fetching a known pain log ID returns the correct entry."""
        created = client.post(
            "/pain-log/", headers=auth_headers, json=_VALID_PAYLOAD
        ).json()
        resp = client.get(f"/pain-log/{created['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]
        assert resp.json()["pain_level"] == created["pain_level"]

    def test_nonexistent_id_returns_404(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A pain log ID that does not exist returns HTTP 404."""
        resp = client.get("/pain-log/999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_cross_user_access_returns_404(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """User A cannot retrieve User B's pain log entry (returns 404, not 403)."""
        created = client.post(
            "/pain-log/", headers=auth_headers, json=_VALID_PAYLOAD
        ).json()

        # Register and log in as a different user
        client.post(
            "/auth/register",
            json={
                "name": "Intruder",
                "email": "intruder_pl@example.com",
                "password": "IntruderPass123!",
            },
        )
        intruder_login = client.post(
            "/auth/login",
            json={
                "email": "intruder_pl@example.com",
                "password": "IntruderPass123!",
            },
        )
        intruder_headers = {
            "Authorization": f"Bearer {intruder_login.json()['access_token']}"
        }
        resp = client.get(f"/pain-log/{created['id']}", headers=intruder_headers)
        assert resp.status_code == 404


# ── DELETE /pain-log/{id} ─────────────────────────────────────────────────────

class TestDeletePainLog:
    """DELETE /pain-log/{id}"""

    def test_delete_own_entry_returns_204(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Deleting an owned pain log entry returns HTTP 204 No Content."""
        created = client.post(
            "/pain-log/", headers=auth_headers, json=_VALID_PAYLOAD
        ).json()
        resp = client.delete(f"/pain-log/{created['id']}", headers=auth_headers)
        assert resp.status_code == 204

    def test_deleted_entry_is_gone(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """After deletion, fetching the same ID returns 404."""
        created = client.post(
            "/pain-log/", headers=auth_headers, json=_VALID_PAYLOAD
        ).json()
        client.delete(f"/pain-log/{created['id']}", headers=auth_headers)
        resp = client.get(f"/pain-log/{created['id']}", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Attempting to delete a non-existent entry returns HTTP 404."""
        resp = client.delete("/pain-log/999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_requires_authentication(self, client: TestClient) -> None:
        """Delete request without a token returns HTTP 401."""
        resp = client.delete("/pain-log/1")
        assert resp.status_code == 401
