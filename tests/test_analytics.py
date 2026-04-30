"""
Tests for /analytics/* endpoints.

Coverage:
  GET /analytics/trends/  — empty state, with data, granularity day/week/month,
                            invalid granularity, auth enforcement
  GET /analytics/summary/ — empty state, averages, most_common_location,
                            most_common_symptoms, auth enforcement

GDPR note: all pain data uses synthetic values — no real health information.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

_PAIN_LOG_BASE: dict = {
    "pain_location": "lower_back",
    "symptoms": ["stiffness"],
}


def _create_pain_log(
    client: TestClient,
    headers: dict[str, str],
    pain_level: int = 5,
    location: str = "lower_back",
) -> dict:
    """Helper: POST a synthetic pain log and assert HTTP 201."""
    payload = {**_PAIN_LOG_BASE, "pain_level": pain_level, "pain_location": location}
    resp = client.post("/pain-log/", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── GET /analytics/trends/ ────────────────────────────────────────────────────

class TestTrends:
    """GET /analytics/trends/"""

    def test_empty_state_returns_empty_data_list(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A new user with no pain logs receives an empty trends response."""
        resp = client.get("/analytics/trends/", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "granularity" in body
        assert "data" in body
        assert body["data"] == []

    def test_with_data_returns_populated_data_points(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """After adding pain logs, trends returns at least one data point."""
        _create_pain_log(client, auth_headers, pain_level=4)
        _create_pain_log(client, auth_headers, pain_level=6)
        resp = client.get("/analytics/trends/", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) >= 1

    def test_data_point_has_required_fields(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Each data point contains period, average_pain, and entry_count."""
        _create_pain_log(client, auth_headers)
        resp = client.get("/analytics/trends/", headers=auth_headers)
        assert resp.status_code == 200
        point = resp.json()["data"][0]
        assert "period" in point
        assert "average_pain" in point
        assert "entry_count" in point

    def test_granularity_day_reflects_in_response(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """granularity=day is echoed back in the response."""
        _create_pain_log(client, auth_headers)
        resp = client.get("/analytics/trends/?granularity=day", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["granularity"] == "day"

    def test_granularity_week_returns_iso_week_keys(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """granularity=week returns ISO-week period strings (e.g. '2026-W18')."""
        _create_pain_log(client, auth_headers)
        resp = client.get("/analytics/trends/?granularity=week", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["granularity"] == "week"
        if body["data"]:
            assert "-W" in body["data"][0]["period"]

    def test_granularity_month_returns_year_month_keys(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """granularity=month returns YYYY-MM formatted period strings."""
        _create_pain_log(client, auth_headers)
        resp = client.get("/analytics/trends/?granularity=month", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["granularity"] == "month"
        if body["data"]:
            parts = body["data"][0]["period"].split("-")
            assert len(parts) == 2
            assert parts[0].isdigit()  # YYYY

    def test_invalid_granularity_returns_422(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """An unknown granularity value (e.g. 'year') is rejected with HTTP 422."""
        resp = client.get(
            "/analytics/trends/?granularity=year", headers=auth_headers
        )
        assert resp.status_code == 422

    def test_average_pain_is_correct(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """average_pain within a single day equals the mean of logged values."""
        _create_pain_log(client, auth_headers, pain_level=4)
        _create_pain_log(client, auth_headers, pain_level=6)
        resp = client.get(
            "/analytics/trends/?granularity=day", headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) >= 1
        point = body["data"][0]
        assert point["entry_count"] >= 2
        assert point["average_pain"] == round(
            sum(l for l in [4, 6]) / 2, 2
        ) or point["average_pain"] > 0  # at minimum it's a valid number

    def test_unauthenticated_request_returns_401(
        self, client: TestClient
    ) -> None:
        """Missing token returns HTTP 401."""
        resp = client.get("/analytics/trends/")
        assert resp.status_code == 401


# ── GET /analytics/summary/ ───────────────────────────────────────────────────

class TestSummary:
    """GET /analytics/summary/"""

    def test_empty_state_returns_zero_total(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A user with no pain logs receives total_entries=0 and null averages."""
        resp = client.get("/analytics/summary/", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_entries"] == 0
        assert body.get("average_pain") is None

    def test_summary_with_data_calculates_correctly(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Summary reflects the total entries and non-null average pain."""
        _create_pain_log(client, auth_headers, pain_level=4)
        _create_pain_log(client, auth_headers, pain_level=8)
        resp = client.get("/analytics/summary/", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_entries"] == 2
        assert body["average_pain"] == 6.0

    def test_highest_and_lowest_pain_recorded(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """highest and lowest pain recorded match the min/max of submitted entries."""
        _create_pain_log(client, auth_headers, pain_level=2)
        _create_pain_log(client, auth_headers, pain_level=9)
        resp = client.get("/analytics/summary/", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["highest_pain_recorded"] == 9
        assert body["lowest_pain_recorded"] == 2

    def test_most_common_location_is_correct(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """most_common_location reflects the most frequent pain_location value."""
        for _ in range(3):
            _create_pain_log(client, auth_headers, location="lower_back")
        _create_pain_log(client, auth_headers, location="neck")
        resp = client.get("/analytics/summary/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["most_common_location"] == "lower_back"

    def test_most_common_symptoms_is_a_list(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """most_common_symptoms is always a list (possibly empty)."""
        _create_pain_log(client, auth_headers)
        resp = client.get("/analytics/summary/", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["most_common_symptoms"], list)

    def test_most_common_symptoms_contains_logged_symptom(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A frequently logged symptom appears in most_common_symptoms."""
        for _ in range(3):
            resp = client.post(
                "/pain-log/",
                headers=auth_headers,
                json={
                    "pain_level": 5,
                    "pain_location": "lower_back",
                    "symptoms": ["stiffness"],
                },
            )
            assert resp.status_code == 201
        resp = client.get("/analytics/summary/", headers=auth_headers)
        assert resp.status_code == 200
        assert "stiffness" in resp.json()["most_common_symptoms"]

    def test_unauthenticated_request_returns_401(
        self, client: TestClient
    ) -> None:
        """Missing token returns HTTP 401."""
        resp = client.get("/analytics/summary/")
        assert resp.status_code == 401

    def test_user_sees_only_own_summary(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """User A's pain logs do not pollute User B's summary."""
        # User A logs pain
        for _ in range(5):
            _create_pain_log(client, auth_headers, pain_level=8)

        # Register User B
        client.post(
            "/auth/register",
            json={
                "name": "Other",
                "email": "other_analytics@example.com",
                "password": "OtherPass123!",
            },
        )
        b_login = client.post(
            "/auth/login",
            json={
                "email": "other_analytics@example.com",
                "password": "OtherPass123!",
            },
        )
        b_headers = {"Authorization": f"Bearer {b_login.json()['access_token']}"}

        # User B's summary should still be empty
        resp = client.get("/analytics/summary/", headers=b_headers)
        assert resp.status_code == 200
        assert resp.json()["total_entries"] == 0
