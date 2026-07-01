"""
API integration tests for /v1/sessions endpoints.

These were entirely untested prior to this change (the only session-related
coverage came indirectly through session_service unit tests). The DB
dependency is overridden per-test to an isolated temp-file SQLite DB, and
the background diagnosis task is patched to a no-op — it uses its own
hardcoded `AsyncSessionFactory` rather than the injected `get_db` dependency
(by design, per its docstring, to avoid closed-session errors after the
request returns), so it can't be pointed at the test DB via dependency
overrides and is out of scope for these endpoint-level tests; the actual
diagnosis logic is covered separately in tests/unit/services/.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.database import Base, get_db
from backend.main import app

VALID_CONFIG = {
    "name": "Test Pipeline",
    "vector_db": {"provider": "chroma", "collection_name": "test_docs"},
    "embedding": {"provider": "openai", "model_id": "text-embedding-3-small"},
    "llm": {"provider": "openai", "model_id": "gpt-4o-mini"},
}
VALID_QUERIES = [{"query": "What is the refund policy?"}]


@pytest.fixture
async def client(tmp_path):
    db_path = tmp_path / "api_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False})

    from backend.db import orm_models  # noqa: F401 — register models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    # The background diagnosis task opens its own DB session against the
    # real global engine, bypassing get_db entirely — patch it to a no-op
    # so these endpoint tests don't touch the real default DB or attempt
    # real network calls to vendor APIs.
    with patch(
        "backend.api.routes.sessions._run_diagnosis_with_own_db",
        new=AsyncMock(return_value=None),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


async def _create_session(client, queries=None) -> str:
    resp = await client.post("/v1/sessions", json={
        "pipeline_config": VALID_CONFIG,
        "queries": queries or VALID_QUERIES,
    })
    assert resp.status_code == 202
    return resp.json()["session_id"]


class TestCreateSession:
    async def test_returns_202_with_session_urls(self, client):
        resp = await client.post("/v1/sessions", json={
            "pipeline_config": VALID_CONFIG,
            "queries": VALID_QUERIES,
        })
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert body["stream_url"] == f"/v1/sessions/{body['session_id']}/stream"
        assert body["report_url"] == f"/v1/sessions/{body['session_id']}/report"

    async def test_invalid_pipeline_config_returns_422(self, client):
        bad_config = {**VALID_CONFIG}
        del bad_config["name"]
        resp = await client.post("/v1/sessions", json={
            "pipeline_config": bad_config,
            "queries": VALID_QUERIES,
        })
        assert resp.status_code == 422
        assert resp.json()["detail"]["message"] == "Invalid pipeline config"

    async def test_empty_query_batch_returns_422(self, client):
        resp = await client.post("/v1/sessions", json={
            "pipeline_config": VALID_CONFIG,
            "queries": [],
        })
        assert resp.status_code == 422


class TestGetSession:
    async def test_returns_pending_status_immediately_after_create(self, client):
        session_id = await _create_session(client)
        resp = await client.get(f"/v1/sessions/{session_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending"
        assert body["completed_queries"] == 0

    async def test_returns_404_for_unknown_session(self, client):
        resp = await client.get("/v1/sessions/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_returns_422_for_malformed_uuid(self, client):
        resp = await client.get("/v1/sessions/not-a-uuid")
        assert resp.status_code == 422


class TestListSessions:
    async def test_lists_created_sessions(self, client):
        id1 = await _create_session(client)
        id2 = await _create_session(client)

        resp = await client.get("/v1/sessions")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert id1 in ids
        assert id2 in ids

    async def test_respects_limit_param(self, client):
        for _ in range(3):
            await _create_session(client)

        resp = await client.get("/v1/sessions", params={"limit": 2})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_empty_when_no_sessions(self, client):
        resp = await client.get("/v1/sessions")
        assert resp.status_code == 200
        assert resp.json() == []


class TestDeleteSession:
    async def test_deletes_existing_session(self, client):
        session_id = await _create_session(client)

        resp = await client.delete(f"/v1/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": session_id}

        follow_up = await client.get(f"/v1/sessions/{session_id}")
        assert follow_up.status_code == 404

    async def test_returns_404_for_unknown_session(self, client):
        resp = await client.delete("/v1/sessions/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_deleting_twice_returns_404_second_time(self, client):
        session_id = await _create_session(client)
        first = await client.delete(f"/v1/sessions/{session_id}")
        second = await client.delete(f"/v1/sessions/{session_id}")
        assert first.status_code == 200
        assert second.status_code == 404
