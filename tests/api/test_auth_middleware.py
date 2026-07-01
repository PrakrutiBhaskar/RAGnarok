"""Tests for ApiKeyAuthMiddleware — opt-in auth for the /v1/* API surface."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.middleware.auth import ApiKeyAuthMiddleware


def make_test_app(api_key: str) -> FastAPI:
    app = FastAPI()
    app.add_middleware(ApiKeyAuthMiddleware, api_key=api_key)

    @app.get("/v1/protected")
    async def protected():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.options("/v1/protected")
    async def preflight():
        return {}

    return app


@pytest.fixture
async def client():
    app = make_test_app(api_key="secret-123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestApiKeyAuthMiddleware:
    async def test_rejects_missing_key(self, client):
        resp = await client.get("/v1/protected")
        assert resp.status_code == 401

    async def test_rejects_wrong_key(self, client):
        resp = await client.get("/v1/protected", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    async def test_accepts_correct_key(self, client):
        resp = await client.get("/v1/protected", headers={"X-API-Key": "secret-123"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    async def test_health_endpoint_bypasses_auth(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_options_preflight_bypasses_auth(self, client):
        resp = await client.options("/v1/protected")
        assert resp.status_code == 200
