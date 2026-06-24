"""
Database setup — SQLAlchemy async engine + session factory.
V1: SQLite (zero-config local tool)
V2 upgrade path: set DATABASE_URL=postgresql://... to switch to PostgreSQL.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# ── Database URL ─────────────────────────────────────────────────────────────

def _get_database_url() -> str:
    """
    Resolve database URL from environment.
    Defaults to SQLite in ~/.rag-debugger/rag_debugger.db
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        # PostgreSQL: swap driver for async
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    # Default: local SQLite
    home = Path(os.environ.get("RAG_DEBUGGER_HOME", Path.home() / ".rag-debugger"))
    home.mkdir(parents=True, exist_ok=True)
    db_path = home / "rag_debugger.db"
    return f"sqlite+aiosqlite:///{db_path}"


DATABASE_URL = _get_database_url()

# ── Engine ───────────────────────────────────────────────────────────────────

_engine_kwargs: dict = {
    "echo": os.environ.get("RAG_DEBUGGER_SQL_ECHO", "").lower() == "true",
}

if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ── ORM base ─────────────────────────────────────────────────────────────────

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


# ── Session dependency (FastAPI) ─────────────────────────────────────────────

async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async database session."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Health check ──────────────────────────────────────────────────────────────

async def check_db_connection() -> bool:
    """Return True if database is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ── Init / teardown ──────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables if they don't exist (dev/test only; use Alembic in prod)."""
    from backend.db import orm_models  # noqa: F401 — import to register models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine connection pool."""
    await engine.dispose()
