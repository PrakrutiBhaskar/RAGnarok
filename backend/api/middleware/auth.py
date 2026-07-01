"""
Optional API key authentication for the /v1/* API surface.

By default, RAGnarok runs entirely unauthenticated — reasonable for its
primary use case (a local CLI/dashboard bound to 127.0.0.1). But the same
FastAPI app is what `docker-compose.yml` starts bound to 0.0.0.0:8765 with
no auth layer at all, which is a real gap the moment this is deployed for
shared/team use rather than solo local use.

This middleware is opt-in: set RAG_DEBUGGER_API_KEY and every request to
/v1/* must include a matching `X-API-Key` header, or receive a 401. Health
checks, docs, and the static dashboard remain reachable without a key so
container orchestrators and the UI shell itself keep working.
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_PROTECTED_PREFIX = "/v1/"


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str) -> None:
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # CORS preflight requests never carry custom headers like
        # X-API-Key — they must reach CORSMiddleware unauthenticated, or
        # every cross-origin browser request (including the dashboard
        # itself, if ever served cross-origin) breaks the moment auth is
        # enabled. Skipping OPTIONS here is more robust than relying on
        # exact middleware registration order.
        if request.method == "OPTIONS":
            return await call_next(request)

        if not request.url.path.startswith(_PROTECTED_PREFIX):
            return await call_next(request)

        provided = request.headers.get("x-api-key", "")
        # Constant-time comparison — this endpoint is reachable pre-auth by
        # design, so a naive `==` would leak key-length/prefix timing.
        if not hmac.compare_digest(provided, self._api_key):
            return JSONResponse(
                {"detail": "Missing or invalid X-API-Key header"},
                status_code=401,
            )

        return await call_next(request)
