"""Tests for /pain-videos endpoints."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient


class TestCreatePainVideo:
    """POST /pain-videos"""

    def test_valid_video_returns_201(
        self, async_client: TestClient, auth_headers_async: dict[str, str], mock_video_analysis
    ) -> None:
        resp = async_client.post(
            "/pain-videos/",
            headers=auth_headers_async,
            files={"file": ("test.mp4", io.BytesIO(b"fake-video"), "video/mp4")},
            data={"duration_seconds": 30},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["overall_pain_estimate"] == 6.0
        assert body["confidence_score"] == 0.75

    def test_unsupported_file_type_returns_400(
        self, async_client: TestClient, auth_headers_async: dict[str, str]
    ) -> None:
        resp = async_client.post(
            "/pain-videos/",
            headers=auth_headers_async,
            files={"file": ("test.txt", io.BytesIO(b"text"), "text/plain")},
        )
        assert resp.status_code == 400

    def test_file_too_large_returns_400(
        self, async_client: TestClient, auth_headers_async: dict[str, str]
    ) -> None:
        big = b"x" * (101 * 1024 * 1024)
        resp = async_client.post(
            "/pain-videos/",
            headers=auth_headers_async,
            files={"file": ("big.mp4", io.BytesIO(big), "video/mp4")},
        )
        assert resp.status_code == 400

    def test_unauthenticated_returns_401(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.post(
            "/pain-videos/",
            files={"file": ("test.mp4", io.BytesIO(b"data"), "video/mp4")},
        )
        assert resp.status_code in (401, 403)


class TestGetPainVideo:
    """GET /pain-videos/{video_id}"""

    def test_returns_analysis(
        self, async_client: TestClient, auth_headers_async: dict[str, str], mock_video_analysis
    ) -> None:
        create_resp = async_client.post(
            "/pain-videos/",
            headers=auth_headers_async,
            files={"file": ("test.mp4", io.BytesIO(b"data"), "video/mp4")},
        )
        vid = create_resp.json()["id"]
        resp = async_client.get(f"/pain-videos/{vid}", headers=auth_headers_async)
        assert resp.status_code == 200
        assert resp.json()["id"] == vid

    def test_nonexistent_returns_404(
        self, async_client: TestClient, auth_headers_async: dict[str, str]
    ) -> None:
        resp = async_client.get("/pain-videos/99999", headers=auth_headers_async)
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(
        self, async_client: TestClient
    ) -> None:
        resp = async_client.get("/pain-videos/1")
        assert resp.status_code in (401, 403)
