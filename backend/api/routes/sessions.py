"""
Session management endpoints.
POST /v1/sessions — create and start a session
GET  /v1/sessions — list sessions
GET  /v1/sessions/{id} — session status
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.models.config import PipelineConfig, QueryBatch
from backend.models.session import CreateSessionRequest, SessionListItem, SessionStatusResponse
from backend.services.session_service import SessionService

logger = logging.getLogger(__name__)
router = APIRouter()


def get_session_service(db: AsyncSession = Depends(get_db)) -> SessionService:
    return SessionService(db)


@router.post("/sessions", status_code=202)
async def create_session(
    body: CreateSessionRequest,
    background_tasks: BackgroundTasks,
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    """
    Create and start a diagnostic session.
    Returns immediately with session_id; diagnosis runs in background.
    Poll GET /v1/sessions/{id} or subscribe to GET /v1/sessions/{id}/stream for progress.
    """
    # Validate pipeline config
    try:
        pipeline_config = PipelineConfig(**body.pipeline_config)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid pipeline config", "errors": e.errors(include_url=False)},
        ) from e

    # Validate query batch
    try:
        query_batch = QueryBatch(queries=body.queries)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid query batch", "errors": e.errors(include_url=False)},
        ) from e

    # Create session record
    session = await service.create_session(
        pipeline_config=pipeline_config,
        query_batch=query_batch,
        redact_pii=body.redact_pii,
    )

    # Run diagnosis in background
    background_tasks.add_task(
        service.run_diagnosis,
        session_id=session.id,
        pipeline_config=pipeline_config,
        query_batch=query_batch,
        redact_pii=body.redact_pii,
    )

    return {
        "session_id": str(session.id),
        "status": "pending",
        "stream_url": f"/v1/sessions/{session.id}/stream",
        "status_url": f"/v1/sessions/{session.id}",
        "report_url": f"/v1/sessions/{session.id}/report",
    }


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    limit: int = 20,
    offset: int = 0,
    service: SessionService = Depends(get_session_service),
) -> list[SessionListItem]:
    """List all sessions, most recent first."""
    return await service.list_sessions(limit=limit, offset=offset)


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> SessionStatusResponse:
    """Get current status and summary for a session."""
    session = await service.get_session(session_id=str(session_id))
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> None:
    """Delete a session and all associated data."""
    deleted = await service.delete_session(session_id=str(session_id))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
