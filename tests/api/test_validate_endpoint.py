"""API integration tests for /v1/validate endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


VALID_CONFIG = {
    "name": "Test Pipeline",
    "vector_db": {"provider": "chroma", "collection_name": "test_docs"},
    "embedding": {"provider": "openai", "model_id": "text-embedding-3-small"},
    "llm": {"provider": "openai", "model_id": "gpt-4o-mini"},
}


class TestValidatePipelineEndpoint:
    async def test_valid_config_returns_200(self, client):
        resp = await client.post("/v1/validate/pipeline", json=VALID_CONFIG)
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert "fingerprint" in body

    async def test_invalid_config_returns_422(self, client):
        bad = {**VALID_CONFIG}
        del bad["name"]
        resp = await client.post("/v1/validate/pipeline", json=bad)
        assert resp.status_code == 422
        body = resp.json()
        assert body["valid"] is False
        assert "errors" in body

    async def test_missing_provider_returns_422(self, client):
        bad = {**VALID_CONFIG, "vector_db": {"provider": "unknown_db", "collection_name": "x"}}
        resp = await client.post("/v1/validate/pipeline", json=bad)
        assert resp.status_code == 422

    async def test_no_prompt_config_returns_warning(self, client):
        resp = await client.post("/v1/validate/pipeline", json=VALID_CONFIG)
        body = resp.json()
        assert any("prompt" in w.lower() for w in body.get("warnings", []))


class TestValidateQueriesEndpoint:
    async def test_valid_queries(self, client):
        resp = await client.post("/v1/validate/queries", json={
            "queries": [{"query": "What is X?"}, {"query": "How does Y work?"}]
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["query_count"] == 2

    async def test_supervised_mode_detected(self, client):
        resp = await client.post("/v1/validate/queries", json={
            "queries": [{"query": "What is X?", "expected_answer": "X is a thing."}]
        })
        assert resp.status_code == 200
        assert resp.json()["mode"] == "supervised"

    async def test_unsupervised_mode_detected(self, client):
        resp = await client.post("/v1/validate/queries", json={
            "queries": [{"query": "What is X?"}]
        })
        assert resp.json()["mode"] == "unsupervised"


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "version" in body
