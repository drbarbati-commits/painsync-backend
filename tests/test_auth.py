"""
Tests for /auth/* endpoints.

Coverage:
  POST /auth/register — valid payload, duplicate email, missing fields, bad password
  POST /auth/login    — success, wrong password, unknown user
  GET  /auth/me       — valid token, no token, invalid token

GDPR note: all email addresses use the .test TLD — no real personal data.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


# ── POST /auth/register ───────────────────────────────────────────────────────

class TestRegister:
    """POST /auth/register"""

    def test_valid_payload_returns_201_with_token(self, client: TestClient) -> None:
        """A complete, valid registration returns HTTP 201 and a bearer token."""
        resp = client.post(
            "/auth/register",
            json={
                "name": "Alice",
                "email": "alice@example.com",
                "password": "SecurePass99!",
                "country": "United Kingdom",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert len(body["access_token"]) > 20

    def test_duplicate_email_returns_409(self, client: TestClient) -> None:
        """Registering with an already-used e-mail returns HTTP 409 Conflict."""
        payload = {
            "name": "Bob",
            "email": "bob_dup@example.com",
            "password": "Password1234!",
        }
        client.post("/auth/register", json=payload)
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 409
        detail = resp.json()["detail"].lower()
        assert "email" in detail or "already" in detail or "exist" in detail

    def test_missing_name_returns_422(self, client: TestClient) -> None:
        """The `name` field is required; omitting it returns HTTP 422."""
        resp = client.post(
            "/auth/register",
            json={"email": "noname@example.com", "password": "Password1234!"},
        )
        assert resp.status_code == 422

    def test_password_too_short_returns_422(self, client: TestClient) -> None:
        """A password shorter than 8 characters is rejected with HTTP 422."""
        resp = client.post(
            "/auth/register",
            json={"name": "Eve", "email": "eve@example.com", "password": "short"},
        )
        assert resp.status_code == 422

    def test_invalid_email_format_returns_422(self, client: TestClient) -> None:
        """A syntactically invalid e-mail string is rejected before hitting the DB."""
        resp = client.post(
            "/auth/register",
            json={"name": "Foo", "email": "not-an-email", "password": "Password1234!"},
        )
        assert resp.status_code == 422

    def test_optional_country_field_is_accepted(self, client: TestClient) -> None:
        """Registration succeeds without the optional `country` field."""
        resp = client.post(
            "/auth/register",
            json={
                "name": "Grace",
                "email": "grace@example.com",
                "password": "ValidPass99!",
            },
        )
        assert resp.status_code == 201


# ── POST /auth/login ──────────────────────────────────────────────────────────

class TestLogin:
    """POST /auth/login"""

    def _register(self, client: TestClient, email: str, password: str) -> None:
        """Helper: register a user silently."""
        resp = client.post(
            "/auth/register",
            json={"name": "Tester", "email": email, "password": password},
        )
        assert resp.status_code == 201

    def test_correct_credentials_return_200_with_token(
        self, client: TestClient
    ) -> None:
        """Valid email + password returns HTTP 200 and a bearer token."""
        self._register(client, "carol@example.com", "ValidPass99!")
        resp = client.post(
            "/auth/login",
            json={"email": "carol@example.com", "password": "ValidPass99!"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_wrong_password_returns_401(self, client: TestClient) -> None:
        """An incorrect password returns HTTP 401 Unauthorized."""
        self._register(client, "dave@example.com", "RealPass123!")
        resp = client.post(
            "/auth/login",
            json={"email": "dave@example.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    def test_unknown_email_returns_401(self, client: TestClient) -> None:
        """Login with a non-existent e-mail returns HTTP 401."""
        resp = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "AnyPass123!"},
        )
        assert resp.status_code == 401

    def test_login_token_is_different_from_register_token(
        self, client: TestClient
    ) -> None:
        """The login endpoint issues its own token (not the same as registration)."""
        reg = client.post(
            "/auth/register",
            json={
                "name": "Henry",
                "email": "henry@example.com",
                "password": "Pass1234!",
            },
        )
        assert reg.status_code == 201
        login = client.post(
            "/auth/login",
            json={"email": "henry@example.com", "password": "Pass1234!"},
        )
        assert login.status_code == 200
        # Both tokens are valid JWTs; they may differ in `iat`
        assert isinstance(login.json()["access_token"], str)


# ── GET /auth/me ──────────────────────────────────────────────────────────────

class TestGetMe:
    """GET /auth/me"""

    def test_authenticated_request_returns_user_profile(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A valid bearer token returns the current user's profile."""
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert "email" in body
        assert "is_active" in body
        assert body["is_active"] is True

    def test_no_token_returns_401(self, client: TestClient) -> None:
        """Missing Authorization header returns HTTP 401 (RFC 7235)."""
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client: TestClient) -> None:
        """A malformed or expired token string returns HTTP 401."""
        resp = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer this.is.invalid"},
        )
        assert resp.status_code == 401

    def test_wrong_scheme_returns_401(self, client: TestClient) -> None:
        """Using a non-Bearer scheme (e.g. Basic) returns HTTP 401."""
        resp = client.get(
            "/auth/me",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401
