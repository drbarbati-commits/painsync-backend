from __future__ import annotations

from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ── Sync engine (existing routes) ──────────────────────────────────────────────

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Async engine (auth routes) — lazy init to allow SQLite test patching ──────

_ASYNC_ENGINE = None
_ASYNC_SESSION_LOCAL = None


def _get_async_engine():
    global _ASYNC_ENGINE
    if _ASYNC_ENGINE is None:
        url = settings.DATABASE_URL
        # Convert sync driver to async driver
        _ASYNC_ENGINE = create_async_engine(
            url.replace("postgresql://", "postgresql+asyncpg://")
            .replace("postgresql+psycopg2://", "postgresql+asyncpg://"),
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _ASYNC_ENGINE


def _get_async_session_local():
    global _ASYNC_SESSION_LOCAL
    if _ASYNC_SESSION_LOCAL is None:
        _ASYNC_SESSION_LOCAL = async_sessionmaker(
            bind=_get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _ASYNC_SESSION_LOCAL


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with _get_async_session_local()() as session:
        try:
            yield session
        finally:
            await session.close()
