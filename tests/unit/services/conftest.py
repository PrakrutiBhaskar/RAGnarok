"""
Fixtures for testing SessionService / ReportService against a real (but
isolated, on-disk temp-file) SQLite database — not the app's global engine,
and not mocked away, since the whole point is exercising the ORM/async
session-handling code paths that the existing suite left untested.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.database import Base


@pytest.fixture
async def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    from backend.db import orm_models  # noqa: F401 — register models on Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncSession:
    factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
