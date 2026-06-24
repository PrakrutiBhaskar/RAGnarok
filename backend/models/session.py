"""Session and query data models (Pydantic, ORM-independent)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


SessionStatus = Literal["pending", "running", "complete", "failed", "partial"]
DiagnosisMode = Literal["supervised", "unsupervised"]

RetrievalVerdict = Literal[
    "RETRIEVAL_OK", "RETRIEVAL_FAIL", "RETRIEVAL_PARTIAL", "DATA_MISSING", "UNKNOWN"
]
GenerationVerdict = Literal[
    "GENERATION_OK", "GENERATION_FAIL", "GENERATION_PARTIAL", "SKIPPED", "UNKNOWN"
]
FinalDiagnosis = Literal[
    "retrieval_failure",
    "generation_failure",
    "compound_failure",
    "data_quality_failure",
    "no_failure_detected",
    "insufficient_evidence",
]

EffortLevel = Literal["low", "medium", "high"]
ImpactLevel = Literal["low", "medium", "high"]


class ChunkEvidence(BaseModel):
    """A retrieved or oracle chunk with scoring evidence."""

    chunk_id: str
    text: str
    cosine_similarity: float | None = None
    bm25_score: float | None = None
    source: Literal["vector_db", "bm25_oracle"] = "vector_db"
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryDiagnosisResult(BaseModel):
    """Per-query diagnosis result produced by the diagnostic engine."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    query_text: str
    expected_answer: str | None = None
    actual_answer: str | None = None

    # Retrieved chunks (from vector DB)
    retrieved_chunks: list[ChunkEvidence] = Field(default_factory=list)
    # Oracle chunks (from BM25)
    oracle_chunks: list[ChunkEvidence] = Field(default_factory=list)

    retrieval_verdict: RetrievalVerdict = "UNKNOWN"
    generation_verdict: GenerationVerdict = "UNKNOWN"
    final_diagnosis: FinalDiagnosis = "insufficient_evidence"
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)

    # Scalar metrics
    max_cosine_similarity: float | None = None
    avg_cosine_similarity: float | None = None
    bm25_score: float | None = None
    expected_answer_in_corpus: bool | None = None

    # Raw evidence for transparency
    evidence: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class Recommendation(BaseModel):
    """A ranked, actionable recommendation produced by the recommendation engine."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    diagnosis_type: FinalDiagnosis
    title: str = Field(..., max_length=200)
    description: str
    effort: EffortLevel
    impact: ImpactLevel
    code_snippet: str | None = None
    rank: int = Field(..., ge=1)
    impact_score: float = Field(0.0, ge=0.0, le=1.0)
    effort_score: float = Field(0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def priority_score(self) -> float:
        """Impact/effort ratio used for ranking (higher = act first)."""
        effort_penalty = 1.0 - (self.effort_score * 0.5)
        return self.impact_score * effort_penalty


class DiagnosisSession(BaseModel):
    """A complete diagnostic session."""

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    pipeline_config_hash: str
    pipeline_config_snapshot: dict[str, Any]

    query_count: int = 0
    status: SessionStatus = "pending"
    mode: DiagnosisMode = "unsupervised"
    overall_confidence: float | None = None

    # Denormalized config fields for quick listing
    db_type: str | None = None
    embedding_provider: str | None = None
    llm_provider: str | None = None
    chunking_strategy: str | None = None
    chunk_size: int | None = None
    top_k: int | None = None

    # Populated after diagnosis
    query_diagnoses: list[QueryDiagnosisResult] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)

    @property
    def failure_distribution(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for qd in self.query_diagnoses:
            counts[qd.final_diagnosis] = counts.get(qd.final_diagnosis, 0) + 1
        return counts

    @property
    def dominant_failure(self) -> FinalDiagnosis | None:
        dist = self.failure_distribution
        if not dist:
            return None
        return max(dist, key=lambda k: dist[k])  # type: ignore[return-value]


# ── API request/response schemas ─────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    """Request body for POST /v1/sessions."""

    pipeline_config: dict[str, Any]   # YAML parsed to dict before sending
    queries: list[dict[str, Any]]
    redact_pii: bool = False
    enable_llm_judge: bool = False


class SessionListItem(BaseModel):
    """Lightweight session item for list endpoints."""

    id: UUID
    created_at: datetime
    status: SessionStatus
    mode: DiagnosisMode
    query_count: int
    db_type: str | None
    embedding_provider: str | None
    llm_provider: str | None
    dominant_failure: str | None
    overall_confidence: float | None


class SessionStatusResponse(BaseModel):
    """Response for GET /v1/sessions/{id}."""

    id: UUID
    status: SessionStatus
    mode: DiagnosisMode
    query_count: int
    completed_queries: int
    overall_confidence: float | None
    failure_distribution: dict[str, int]
    created_at: datetime
    updated_at: datetime
