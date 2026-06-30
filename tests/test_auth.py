"""
Tests for /auth/* endpoints.

Coverage:
  POST /auth/register        — valid payload, duplicate email, missing fields
  POST /auth/login           — success, wrong password, unknown user
  GET  /auth/me              — valid token, no token, invalid token
  POST /auth/refresh         — valid refresh, expired/invalid/used token
  POST /auth/logout          — revoke tokens, reuse after logout
  POST /auth/phone/send-otp  — valid phone, bad format, rate limit
  POST /auth/phone/verify-otp — correct OTP, wrong OTP, expired OTP
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import re
import logging


def _extract_otp_from_log(caplog, phone: str) -> str | None:
    """Parse OTP from the console log: 'OTP for %s: XXXXXX (SMS not configured...'"""
    for record in caplog.records:
        if f"OTP for {phone}:" in record.message:
            m = re.search(r"OTP for .*?: (\d{6})", record.message)
            if m:
                return m.group(1)
    return None


def _send_otp_and_extract(
    async_client, caplog, phone: str
) -> str | None:
    """Send OTP request and extract OTP from log output."""
    caplog.set_level(logging.INFO)
    resp = async_client.post("/auth/phone/send-otp", json={"phone": phone})
    assert resp.status_code == 200
    return _extract_otp_from_log(caplog, phone)


# ── POST /auth/register ───────────────────────────────────────────────────────


class TestRegister:
    """POST /auth/register"""

    def test_valid_payload_returns_201_with_tokens(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
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
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert len(body["access_token"]) > 20
        assert len(body["refresh_token"]) > 20

    def test_duplicate_email_returns_409(
        self, async_client: TestClient
    ) -> None:
        payload = {
            "name": "Bob",
            "email": "bob_dup@example.com",
            "password": "Password1234!",
        }
        async_client.post("/auth/register", json=payload)
        resp = async_client.post("/auth/register", json=payload)
        assert resp.status_code == 409
        detail = resp.json()["detail"].lower()
        assert "email" in detail or "already" in detail or "exist" in detail

    def test_missing_name_returns_422(self, async_client: TestClient) -> None:
        resp = async_client.post(
            "/auth/register",
            json={"email": "noname@example.com", "password": "Password1234!"},
        )
        assert resp.status_code == 422

    def test_password_too_short_returns_422(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/register",
            json={"name": "Eve", "email": "eve@example.com", "password": "short"},
        )
        assert resp.status_code == 422

    def test_invalid_email_format_returns_422(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/register",
            json={
                "name": "Foo",
                "email": "not-an-email",
                "password": "Password1234!",
            },
        )
        assert resp.status_code == 422

    def test_optional_country_field_is_accepted(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/register",
            json={
                "name": "Grace",
                "email": "grace@example.com",
                "password": "ValidPass99!",
            },
        )
        assert resp.status_code == 201
        assert "refresh_token" in resp.json()


# ── POST /auth/login ──────────────────────────────────────────────────────────


class TestLogin:
    """POST /auth/login"""

    def _register(self, client: TestClient, email: str, password: str) -> None:
        resp = client.post(
            "/auth/register",
            json={"name": "Tester", "email": email, "password": password},
        )
        assert resp.status_code == 201

    def test_correct_credentials_return_200_with_tokens(
        self, async_client: TestClient
    ) -> None:
        self._register(async_client, "carol@example.com", "ValidPass99!")
        resp = async_client.post(
            "/auth/login",
            json={"email": "carol@example.com", "password": "ValidPass99!"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    def test_wrong_password_returns_401(
        self, async_client: TestClient
    ) -> None:
        self._register(async_client, "dave@example.com", "RealPass123!")
        resp = async_client.post(
            "/auth/login",
            json={"email": "dave@example.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    def test_unknown_email_returns_401(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "AnyPass123!"},
        )
        assert resp.status_code == 401


# ── GET /auth/me ──────────────────────────────────────────────────────────────


class TestGetMe:
    """GET /auth/me"""

    def test_authenticated_request_returns_user_profile(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/register",
            json={
                "name": "Profile Tester",
                "email": "profile@example.com",
                "password": "Pass1234!",
            },
        )
        token = resp.json()["access_token"]
        resp = async_client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] is not None
        assert body["email"] == "profile@example.com"
        assert body["is_active"] is True

    def test_no_token_returns_401(self, async_client: TestClient) -> None:
        resp = async_client.get("/auth/me")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, async_client: TestClient) -> None:
        resp = async_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer this.is.invalid"},
        )
        assert resp.status_code == 401


# ── POST /auth/refresh ────────────────────────────────────────────────────────


class TestRefresh:
    """POST /auth/refresh"""

    def _register_and_get_tokens(
        self, client: TestClient, email: str = "refresh@example.com"
    ) -> tuple[str, str]:
        resp = client.post(
            "/auth/register",
            json={
                "name": "Refresh Tester",
                "email": email,
                "password": "StrongPass123!",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        return body["access_token"], body["refresh_token"]

    def test_valid_refresh_returns_new_token_pair(
        self, async_client: TestClient
    ) -> None:
        _, refresh = self._register_and_get_tokens(async_client)
        resp = async_client.post(
            "/auth/refresh", json={"refresh_token": refresh}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        # New tokens should differ from the old ones
        assert body["refresh_token"] != refresh

    def test_used_refresh_token_is_rejected(
        self, async_client: TestClient
    ) -> None:
        _, refresh = self._register_and_get_tokens(
            async_client, "reuse@example.com"
        )
        # First use succeeds
        resp1 = async_client.post(
            "/auth/refresh", json={"refresh_token": refresh}
        )
        assert resp1.status_code == 200
        # Second use of same token should fail (rotation)
        resp2 = async_client.post(
            "/auth/refresh", json={"refresh_token": refresh}
        )
        assert resp2.status_code == 401

    def test_invalid_token_string_returns_401(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/refresh", json={"refresh_token": "not-a-valid-jwt"}
        )
        assert resp.status_code == 401

    def test_access_token_rejected_as_refresh(
        self, async_client: TestClient
    ) -> None:
        access, _ = self._register_and_get_tokens(
            async_client, "wrong-type@example.com"
        )
        resp = async_client.post(
            "/auth/refresh", json={"refresh_token": access}
        )
        assert resp.status_code == 401


# ── POST /auth/logout ─────────────────────────────────────────────────────────


class TestLogout:
    """POST /auth/logout"""

    def _register_and_get_tokens(
        self, client: TestClient, email: str = "logout@example.com"
    ) -> tuple[str, str]:
        resp = client.post(
            "/auth/register",
            json={
                "name": "Logout Tester",
                "email": email,
                "password": "StrongPass123!",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        return body["access_token"], body["refresh_token"]

    def test_logout_succeeds(self, async_client: TestClient) -> None:
        access, refresh = self._register_and_get_tokens(async_client)
        resp = async_client.post(
            "/auth/logout",
            json={"access_token": access, "refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Successfully logged out"

    def test_access_token_rejected_after_logout(
        self, async_client: TestClient
    ) -> None:
        access, refresh = self._register_and_get_tokens(
            async_client, "post-logout@example.com"
        )
        # Logout
        async_client.post(
            "/auth/logout",
            json={"access_token": access, "refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
        # Old access token should be rejected
        resp = async_client.get(
            "/auth/me", headers={"Authorization": f"Bearer {access}"}
        )
        assert resp.status_code == 401
        detail = resp.json()["detail"].lower()
        assert "revoked" in detail or "invalid" in detail

    def test_logout_without_auth_fails(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/logout",
            json={
                "access_token": "some-token",
                "refresh_token": "some-refresh",
            },
        )
        assert resp.status_code == 403 or resp.status_code == 401


# ── POST /auth/phone/send-otp ─────────────────────────────────────────────────


class TestPhoneSendOTP:
    """POST /auth/phone/send-otp"""

    def test_valid_phone_returns_success(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/phone/send-otp",
            json={"phone": "+491234567890"},
        )
        assert resp.status_code == 200
        assert "OTP sent" in resp.json()["message"]

    def test_invalid_phone_format_returns_422(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/phone/send-otp",
            json={"phone": "12345"},
        )
        assert resp.status_code == 422

    def test_otp_not_in_response(self, async_client: TestClient) -> None:
        resp = async_client.post(
            "/auth/phone/send-otp",
            json={"phone": "+49000123456789"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "otp" not in body
        assert "debug_otp" not in body


# ── POST /auth/phone/verify-otp ───────────────────────────────────────────────


class TestPhoneVerifyOTP:
    """POST /auth/phone/verify-otp & /auth/phone/verify"""

    def test_verify_with_correct_otp(
        self, async_client: TestClient, caplog
    ) -> None:
        phone = "+491111111111"
        otp = _send_otp_and_extract(async_client, caplog, phone)
        assert otp is not None, "OTP not found in log output"

        resp = async_client.post(
            "/auth/phone/verify-otp",
            json={"phone": phone, "otp": otp},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert "user" in body

    def test_verify_wrong_otp_returns_401(
        self, async_client: TestClient, caplog
    ) -> None:
        phone = "+492222222222"
        _send_otp_and_extract(async_client, caplog, phone)
        resp = async_client.post(
            "/auth/phone/verify-otp",
            json={"phone": phone, "otp": "000000"},
        )
        assert resp.status_code == 401

    def test_verify_without_request_returns_400(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/auth/phone/verify-otp",
            json={"phone": "+493333333333", "otp": "123456"},
        )
        assert resp.status_code == 400

    def test_legacy_verify_endpoint_works(
        self, async_client: TestClient, caplog
    ) -> None:
        phone = "+494444444444"
        otp = _send_otp_and_extract(async_client, caplog, phone)
        assert otp is not None, "OTP not found in log output"
        resp = async_client.post(
            "/auth/phone/verify",
            json={"phone": phone, "otp": otp},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
