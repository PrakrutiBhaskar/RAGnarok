"""
SSE streaming endpoint.
GET /v1/sessions/{id}/stream — real-time diagnosis progress via Server-Sent Events.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.models.report import StreamEvent
from backend.services.session_service import SessionService

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory event bus: session_id → list of pending SSE payloads
# In production this would be Redis pub/sub; for local use in-process is fine.
_event_queues: dict[str, asyncio.Queue] = {}


def get_event_queue(session_id: str) -> asyncio.Queue:
    if session_id not in _event_queues:
        _event_queues[session_id] = asyncio.Queue(maxsize=1000)
    return _event_queues[session_id]


def publish_event(session_id: str, event: StreamEvent) -> None:
    """Called by SessionService to push progress events to connected SSE clients."""
    queue = get_event_queue(session_id)
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning("SSE queue full for session %s — dropping event", session_id)


@router.get("/sessions/{session_id}/stream")
async def stream_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Stream diagnosis progress as Server-Sent Events.
    Clients receive one event per query diagnosed, plus a final session_complete event.
    """
    service = SessionService(db)
    session = await service.get_session(str(session_id))
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # If already complete, stream a single summary event
    if session.status in ("complete", "partial", "failed"):
        async def completed_stream():
            event = StreamEvent(
                event="session_complete",
                session_id=str(session_id),
                total_queries=session.query_count,
            )
            yield event.to_sse()

        return StreamingResponse(
            completed_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    queue = get_event_queue(str(session_id))

    async def event_generator():
        # Heartbeat to keep connection alive
        heartbeat_interval = 15  # seconds
        last_heartbeat = asyncio.get_event_loop().time()

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield event.to_sse()

                if event.event == "session_complete" or event.event == "error":
                    # Clean up queue after session ends
                    _event_queues.pop(str(session_id), None)
                    break
            except asyncio.TimeoutError:
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat > heartbeat_interval:
                    heartbeat = StreamEvent(
                        event="heartbeat",
                        session_id=str(session_id),
                        timestamp=datetime.utcnow(),
                    )
                    yield heartbeat.to_sse()
                    last_heartbeat = now
            except Exception as e:
                logger.error("SSE stream error for session %s: %s", session_id, e)
                error_event = StreamEvent(
                    event="error",
                    session_id=str(session_id),
                    error=str(e),
                )
                yield error_event.to_sse()
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
