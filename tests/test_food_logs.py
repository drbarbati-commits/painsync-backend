"""Tests for /food-logs endpoints."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


class TestCreateFoodLog:
    """POST /food-logs"""

    def test_valid_image_returns_201(
        self, async_client: TestClient, auth_headers_async: dict[str, str], mock_food_analysis
    ) -> None:
        resp = async_client.post(
            "/food-logs/",
            headers=auth_headers_async,
            files={"file": ("test.jpg", io.BytesIO(b"fake-image"), "image/jpeg")},
            data={"meal_type": "lunch"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["meal_type"] == "lunch"

    def test_unsupported_file_type_returns_400(
        self, async_client: TestClient, auth_headers_async: dict[str, str]
    ) -> None:
        resp = async_client.post(
            "/food-logs/",
            headers=auth_headers_async,
            files={"file": ("test.txt", io.BytesIO(b"text"), "text/plain")},
        )
        assert resp.status_code == 400

    def test_file_too_large_returns_400(
        self, async_client: TestClient, auth_headers_async: dict[str, str]
    ) -> None:
        big = b"x" * (11 * 1024 * 1024)
        resp = async_client.post(
            "/food-logs/",
            headers=auth_headers_async,
            files={"file": ("big.jpg", io.BytesIO(big), "image/jpeg")},
        )
        assert resp.status_code == 400

    def test_unauthenticated_returns_401(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/food-logs/",
            files={"file": ("test.jpg", io.BytesIO(b"data"), "image/jpeg")},
        )
        assert resp.status_code == 403 or resp.status_code == 401


class TestListFoodLogs:
    """GET /food-logs"""

    def test_returns_paginated_list(
        self, async_client: TestClient, auth_headers_async: dict[str, str], mock_food_analysis
    ) -> None:
        async_client.post(
            "/food-logs/",
            headers=auth_headers_async,
            files={"file": ("a.jpg", io.BytesIO(b"data"), "image/jpeg")},
        )
        resp = async_client.get("/food-logs/", headers=auth_headers_async)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert body["total"] >= 1

    def test_empty_list_for_new_user(
        self, async_client: TestClient, auth_headers_async: dict[str, str]
    ) -> None:
        resp = async_client.get("/food-logs/", headers=auth_headers_async)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_unauthenticated_returns_401(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.get("/food-logs/")
        assert resp.status_code in (401, 403)
