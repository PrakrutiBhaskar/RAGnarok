"""Report output models — structured JSON and markdown report schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from backend.models.session import (
    FinalDiagnosis,
    QueryDiagnosisResult,
    Recommendation,
    SessionStatus,
)


class ReportSummary(BaseModel):
    """Top-level summary section of the report."""

    total_queries: int
    failure_distribution: dict[str, int]
    dominant_failure: FinalDiagnosis | None
    overall_confidence: float | None
    mode: str  # supervised / unsupervised
    low_confidence_count: int = 0  # queries where confidence < 0.5


class DiagnosisReport(BaseModel):
    """
    Complete structured diagnosis report.
    Serializes to JSON (GET /v1/sessions/{id}/report)
    and renders to Markdown (GET /v1/sessions/{id}/report.md).
    """

    report_version: str = "1.0"
    session_id: UUID
    pipeline_name: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    status: SessionStatus
    duration_seconds: float | None = None

    summary: ReportSummary
    query_diagnoses: list[QueryDiagnosisResult]
    recommendations: list[Recommendation]

    # Pipeline snapshot for reproducibility
    pipeline_snapshot: dict[str, Any] = Field(default_factory=dict)

    # Flags
    low_confidence_flag: bool = False   # any query with confidence < 0.5
    data_sharing_notice: str | None = None  # set when LLM judge was used


class StreamEvent(BaseModel):
    """
    Server-Sent Event payload for real-time progress streaming.
    Sent via GET /v1/sessions/{id}/stream
    """

    event: str  # "query_complete" | "session_complete" | "error" | "heartbeat"
    session_id: str
    query_index: int | None = None
    total_queries: int | None = None
    query_text: str | None = None
    diagnosis: str | None = None
    confidence: float | None = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_sse(self) -> str:
        """Format as SSE wire format."""
        import json
        data = self.model_dump(mode="json", exclude_none=True)
        return f"event: {self.event}\ndata: {json.dumps(data)}\n\n"
