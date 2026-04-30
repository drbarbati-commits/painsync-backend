"""
Pytest configuration and shared fixtures for PainSync backend tests.

Environment variables are injected before any app module is imported so that
pydantic-settings can initialise without a real .env file.  The test database
uses in-memory SQLite; PostgreSQL-specific ARRAY columns are shimmed with a
JSON-backed TypeDecorator so CREATE TABLE and DML work on SQLite.
"""
from __future__ import annotations

import json
import os
from collections.abc import Generator

# ── 1. Required env vars BEFORE any `app.*` import ───────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used-in-tests")

# ── 1b. SQLite compat patch ───────────────────────────────────────────────────
# app/core/database.py passes pool_size / max_overflow to create_engine.
# Those kwargs are PostgreSQL/QueuePool-specific and crash SQLite's
# SingletonThreadPool.  Patch sqlalchemy.create_engine at module level (before
# any app import) so unsupported kwargs are silently dropped for SQLite.
import sqlalchemy as _sa

_orig_create_engine = _sa.create_engine
_SQLITE_UNSUPPORTED = {"pool_size", "max_overflow"}


def _sqlite_safe_create_engine(url: object, **kw: object) -> object:
    """Wrapper that strips PostgreSQL-only pool kwargs when the dialect is SQLite."""
    if str(url).startswith("sqlite"):
        for key in _SQLITE_UNSUPPORTED:
            kw.pop(key, None)
    return _orig_create_engine(url, **kw)  # type: ignore[arg-type]


_sa.create_engine = _sqlite_safe_create_engine  # type: ignore[assignment]

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import Text, TypeDecorator

from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.models.wellness import WaterLog


# ── 2. ARRAY→JSON shim for SQLite (ARRAY is PostgreSQL-only) ─────────────────

class _JsonList(TypeDecorator):
    """Stores a Python list as a JSON string in SQLite test databases."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # Python → DB
        if value is None:
            return "[]"
        return json.dumps(value)

    def process_result_value(self, value, dialect):  # DB → Python
        if not value:
            return []
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return []


def _patch_array_columns() -> None:
    """Replace ARRAY column types with _JsonList before any table DDL runs."""
    from app.models.pain_log import PainLog          # noqa: PLC0415
    from app.models.triage import TriageAssessment   # noqa: PLC0415

    for col in (
        PainLog.__table__.c.pain_locations,
        PainLog.__table__.c.symptoms,
        TriageAssessment.__table__.c.symptoms,
    ):
        col.type = _JsonList()


_patch_array_columns()

# Import patched models so their tables are visible in Base.metadata
from app.models.pain_log import PainLog            # noqa: E402
from app.models.triage import TriageAssessment     # noqa: E402

# Tables to create for tests (FK order is resolved by SQLAlchemy automatically)
_TEST_TABLES = [
    User.__table__,
    WaterLog.__table__,
    PainLog.__table__,
    TriageAssessment.__table__,
]


# ── 3. Database fixtures ──────────────────────────────────────────────────────

@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Fresh in-memory SQLite database for every test function."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=_TEST_TABLES)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine, tables=_TEST_TABLES)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with get_db overridden to use the test session."""

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── 4. Auth helpers ───────────────────────────────────────────────────────────

def _register_and_login(
    client: TestClient,
    email: str = "testuser@example.com",
    password: str = "StrongPass123!",
    name: str = "Test User",
    country: str = "United Kingdom",
) -> str:
    """Register (or skip if duplicate) and return a valid JWT access token."""
    resp = client.post(
        "/auth/register",
        json={"name": name, "email": email, "password": password, "country": country},
    )
    if resp.status_code == 409:
        resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code in (200, 201), f"Auth setup failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    """Bearer token headers for a freshly registered test user."""
    token = _register_and_login(client)
    return {"Authorization": f"Bearer {token}"}


# ── 5. AI mock fixture ────────────────────────────────────────────────────────

@pytest.fixture()
def mock_claude(mocker):
    """
    Mock the triage AI call so no real API credits are consumed.
    Returns a fixed, deterministic triage payload.
    """
    return mocker.patch(
        "app.api.routes.triage.triage_with_ai",
        return_value={
            "urgency": "routine",
            "recommendation": "Apply heat, rest, and monitor symptoms.",
            "reasoning": "Moderate pain with no emergency indicators.",
            "model_used": "mock-model",
        },
    )
