"""
Pytest configuration and shared fixtures for PainSync backend tests.
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator, Generator

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used-in-tests")

import sqlalchemy as _sa

_orig_create_engine = _sa.create_engine
_SQLITE_UNSUPPORTED = {"pool_size", "max_overflow"}


def _sqlite_safe_create_engine(url: object, **kw: object) -> object:
    if str(url).startswith("sqlite"):
        for key in _SQLITE_UNSUPPORTED:
            kw.pop(key, None)
    return _orig_create_engine(url, **kw)


_sa.create_engine = _sqlite_safe_create_engine

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import Text, TypeDecorator

from app.core.database import Base, get_db, get_async_db
from app.core.config import settings
from app.main import app
from app.models.user import User
from app.models.wellness import WaterLog
from app.models.security import TokenBlacklist, OTPCode

# ── ARRAY→JSON shim ─────────────────────────────────────────────────────────


class _JsonList(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "[]"
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if not value:
            return []
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return []


def _patch_array_columns() -> None:
    from app.models.pain_log import PainLog
    from app.models.triage import TriageAssessment

    for col in (
        PainLog.__table__.c.pain_locations,
        PainLog.__table__.c.symptoms,
        TriageAssessment.__table__.c.symptoms,
        User.__table__.c.pain_areas,
    ):
        col.type = _JsonList()


_patch_array_columns()

from app.models.pain_log import PainLog
from app.models.triage import TriageAssessment
from app.models.wellness import FoodLog, PainVideoAnalysis
from app.models.chat import ChatSession, ChatMessage

_ALL_TABLES = [
    User.__table__,
    WaterLog.__table__,
    FoodLog.__table__,
    PainVideoAnalysis.__table__,
    PainLog.__table__,
    TriageAssessment.__table__,
    TokenBlacklist.__table__,
    OTPCode.__table__,
    ChatSession.__table__,
    ChatMessage.__table__,
]

# ── Shared engines ──────────────────────────────────────────────────────────
# Temp file so sync + async engines access the same database.
import tempfile

_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TEST_DB.close()

SYNC_ENGINE = create_engine(
    f"sqlite+pysqlite:///{_TEST_DB.name}",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SyncSession = sessionmaker(autocommit=False, autoflush=False, bind=SYNC_ENGINE)

ASYNC_ENGINE = create_async_engine(f"sqlite+aiosqlite:///{_TEST_DB.name}")


def _init_tables() -> None:
    Base.metadata.create_all(bind=SYNC_ENGINE, tables=_ALL_TABLES)


async def _init_async_tables() -> None:
    async with ASYNC_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _drop_tables() -> None:
    Base.metadata.drop_all(bind=SYNC_ENGINE, tables=_ALL_TABLES)


async def _drop_async_tables() -> None:
    async with ASYNC_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Sync fixtures (existing tests) ─────────────────────────────────────────


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    _init_tables()
    session = SyncSession()
    try:
        yield session
    finally:
        session.close()
        _drop_tables()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    import asyncio
    asyncio.run(_init_async_tables())

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    async def override_get_async_db() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(bind=ASYNC_ENGINE) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

    from app.middleware.rate_limit import _windows

    _windows.clear()
    asyncio.run(_drop_async_tables())


# ── Async fixtures (new auth tests) ────────────────────────────────────────


@pytest.fixture()
async def async_client() -> AsyncGenerator[TestClient, None, None]:
    """TestClient that creates a fresh async aiosqlite DB per test."""
    await _init_async_tables()
    app.dependency_overrides[get_async_db] = _make_async_db_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    await _drop_async_tables()

    from app.middleware.rate_limit import _windows as mw_windows
    mw_windows.clear()
    from app.api.routes.auth import (
        _otp_send_windows,
        _otp_verify_windows,
        _refresh_rate_windows,
    )
    _otp_send_windows.clear()
    _otp_verify_windows.clear()
    _refresh_rate_windows.clear()


async def _make_async_db_override() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh AsyncSession bound to the shared test ASYNC_ENGINE."""
    async with AsyncSession(
        bind=ASYNC_ENGINE, expire_on_commit=False
    ) as session:
        yield session


# ── Auth helpers ────────────────────────────────────────────────────────────


def _register_and_login(
    client: TestClient,
    email: str = "testuser@example.com",
    password: str = "StrongPass123!",
    name: str = "Test User",
    country: str = "United Kingdom",
) -> tuple[str, str]:
    """Register and return (access_token, refresh_token)."""
    resp = client.post(
        "/auth/register",
        json={"name": name, "email": email, "password": password, "country": country},
    )
    if resp.status_code == 409:
        resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code in (200, 201), f"Auth setup failed: {resp.text}"
    body = resp.json()
    return body["access_token"], body.get("refresh_token", "")


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    token, _ = _register_and_login(client)
    return {"Authorization": f"Bearer {token}"}


# ── AI mock fixture ────────────────────────────────────────────────────────


@pytest.fixture()
def auth_headers_async(async_client: TestClient) -> dict[str, str]:
    token, _ = _register_and_login(async_client)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def mock_claude(mocker):
    return mocker.patch(
        "app.api.routes.triage.triage_with_ai",
        return_value={
            "urgency": "routine",
            "recommendation": "Apply heat, rest, and monitor symptoms.",
            "reasoning": "Moderate pain with no emergency indicators.",
            "model_used": "mock-model",
        },
    )


@pytest.fixture()
def mock_food_analysis(mocker):
    return mocker.patch(
        "app.api.routes.food_logs.analyze_food_image",
        return_value={
            "food_description": "grilled chicken, rice, broccoli",
            "estimated_calories": 550,
            "estimated_protein_g": 45,
            "estimated_carbs_g": 60,
            "estimated_fat_g": 12,
            "ai_notes": "Balanced meal with anti-inflammatory ingredients.",
        },
    )


@pytest.fixture()
def mock_video_analysis(mocker):
    return mocker.patch(
        "app.api.routes.pain_videos.analyze_pain_video",
        return_value={
            "facial_pain_score": 6.5,
            "voice_pain_indicators": "Tense vocal quality, occasional groaning",
            "behavioral_indicators": "Guarded movement, favoring left side",
            "overall_pain_estimate": 6.0,
            "ai_observations": "Patient displays moderate pain indicators during movement.",
            "confidence_score": 0.75,
        },
    )
