"""
FastAPI application factory.
All routes registered here. Serves as the entry point for the local web UI server.
"""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
# Search for .env in multiple locations
for _env_path in [Path(__file__).parent.parent / ".env", Path.cwd() / ".env", Path(".env")]:
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
        break

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.db.database import check_db_connection, close_db, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    settings.ensure_home_dir()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("RAG Debugger %s starting up", settings.version)

    if settings.host not in ("127.0.0.1", "localhost") and not settings.api_key:
        logger.warning(
            "Server is bound to %s (not localhost) with no RAG_DEBUGGER_API_KEY "
            "set — every /v1/* endpoint is reachable by anyone with network "
            "access, with no authentication. Set RAG_DEBUGGER_API_KEY to require "
            "an X-API-Key header, or bind to 127.0.0.1 for local-only use.",
            settings.host,
        )

    # Initialize database
    await init_db()
    db_ok = await check_db_connection()
    if not db_ok:
        logger.error("Database connection failed on startup")
    else:
        logger.info("Database connection OK")

    yield

    # Cleanup
    await close_db()
    logger.info("RAG Debugger shut down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="RAG Quality Debugger",
        description="Automated diagnostic tool for RAG pipeline failure attribution",
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Optional API key auth for /v1/* — opt-in via RAG_DEBUGGER_API_KEY.
    # (ApiKeyAuthMiddleware explicitly skips OPTIONS requests, so its
    # position relative to CORSMiddleware below doesn't affect preflight.)

    # CORS — only localhost origins (local tool, no CSRF risk)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",   # Vite dev server
            "http://localhost:8765",   # Production UI
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8765",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.api_key:
        from backend.api.middleware.auth import ApiKeyAuthMiddleware
        app.add_middleware(ApiKeyAuthMiddleware, api_key=settings.api_key)
        logger.info("API key auth enabled for /v1/* (RAG_DEBUGGER_API_KEY is set)")

    # Register routes
    from backend.api.routes import sessions, reports, stream, validate
    app.include_router(sessions.router, prefix="/v1", tags=["Sessions"])
    app.include_router(reports.router, prefix="/v1", tags=["Reports"])
    app.include_router(stream.router, prefix="/v1", tags=["Stream"])
    app.include_router(validate.router, prefix="/v1", tags=["Validate"])

    @app.get("/health", tags=["Health"])
    async def health() -> JSONResponse:
        db_ok = await check_db_connection()
        return JSONResponse({
            "status": "ok" if db_ok else "degraded",
            "version": settings.version,
            "db": "ok" if db_ok else "error",
        })

    # Serve the built React dashboard, if present (Docker image bakes this in
    # via the frontend-builder stage; local dev typically runs `vite dev` on
    # a separate port instead, so this is a no-op unless frontend/dist exists).
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dist), html=True),
            name="dashboard",
        )
        logger.info("Serving frontend dashboard from %s", frontend_dist)
    else:
        @app.get("/", tags=["Root"])
        async def root() -> JSONResponse:
            return JSONResponse({
                "name": "RAG Quality Debugger",
                "version": settings.version,
                "docs": "/docs",
                "ui": f"http://localhost:{settings.port}",
                "note": "frontend/dist not found — run `npm run build` in frontend/ "
                        "or use the Docker image, which builds it automatically.",
            })

    return app


# Application instance
app = create_app()