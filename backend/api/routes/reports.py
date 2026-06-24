"""
Report endpoints.
GET /v1/sessions/{id}/report      — JSON report
GET /v1/sessions/{id}/report.md  — Markdown report
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.models.report import DiagnosisReport
from backend.services.report_service import ReportService
from backend.services.session_service import SessionService

router = APIRouter()


def get_services(db: AsyncSession = Depends(get_db)):
    return SessionService(db), ReportService(db)


@router.get("/sessions/{session_id}/report", response_model=DiagnosisReport)
async def get_report_json(
    session_id: UUID,
    services=Depends(get_services),
) -> DiagnosisReport:
    """Get the full structured JSON report for a completed session."""
    session_service, report_service = services
    session = await session_service.get_session_full(str(session_id))
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session.status not in ("complete", "partial"):
        raise HTTPException(
            status_code=409,
            detail=f"Session is not yet complete (status={session.status}). "
                   "Poll /v1/sessions/{id} or stream /v1/sessions/{id}/stream for progress.",
        )
    return await report_service.build_report(session)


@router.get("/sessions/{session_id}/report.md", response_class=PlainTextResponse)
async def get_report_markdown(
    session_id: UUID,
    services=Depends(get_services),
) -> str:
    """Get the Markdown-formatted report for a completed session."""
    session_service, report_service = services
    session = await session_service.get_session_full(str(session_id))
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session.status not in ("complete", "partial"):
        raise HTTPException(
            status_code=409,
            detail=f"Session is not yet complete (status={session.status}).",
        )
    report = await report_service.build_report(session)
    return report_service.render_markdown(report)
