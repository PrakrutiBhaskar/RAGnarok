"""
SQLAlchemy ORM models — table definitions matching the SQL schema in Section 5.2.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DiagnosisSessionORM(Base):
    __tablename__ = "diagnosis_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    pipeline_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_config_snapshot: Mapped[dict | None] = mapped_column(JSON)
    query_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(20), default="unsupervised", nullable=False)
    overall_confidence: Mapped[float | None] = mapped_column(Float)
    db_type: Mapped[str | None] = mapped_column(String(50))
    embedding_provider: Mapped[str | None] = mapped_column(String(50))
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    chunking_strategy: Mapped[str | None] = mapped_column(String(50))
    chunk_size: Mapped[int | None] = mapped_column(Integer)
    top_k: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("status IN ('pending','running','complete','failed','partial')", name="ck_sessions_status"),
        CheckConstraint("mode IN ('supervised','unsupervised')", name="ck_sessions_mode"),
        CheckConstraint("top_k BETWEEN 1 AND 50", name="ck_sessions_top_k"),
        CheckConstraint("chunk_size BETWEEN 64 AND 8192", name="ck_sessions_chunk_size"),
    )

    # Relationships
    query_diagnoses: Mapped[list[QueryDiagnosisORM]] = relationship(
        "QueryDiagnosisORM", back_populates="session", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list[RecommendationORM]] = relationship(
        "RecommendationORM", back_populates="session", cascade="all, delete-orphan"
    )


class QueryDiagnosisORM(Base):
    __tablename__ = "query_diagnoses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("diagnosis_sessions.id", ondelete="CASCADE"), nullable=False
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str | None] = mapped_column(Text)
    actual_answer: Mapped[str | None] = mapped_column(Text)
    retrieved_chunks: Mapped[list] = mapped_column(JSON, default=list)
    oracle_chunks: Mapped[list | None] = mapped_column(JSON)
    retrieval_verdict: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    generation_verdict: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    final_diagnosis: Mapped[str] = mapped_column(String(30), nullable=False, default="insufficient_evidence")
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_cosine_similarity: Mapped[float | None] = mapped_column(Float)
    avg_cosine_similarity: Mapped[float | None] = mapped_column(Float)
    bm25_score: Mapped[float | None] = mapped_column(Float)
    expected_answer_in_corpus: Mapped[bool | None] = mapped_column(Boolean)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    session: Mapped[DiagnosisSessionORM] = relationship("DiagnosisSessionORM", back_populates="query_diagnoses")


class RecommendationORM(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("diagnosis_sessions.id", ondelete="CASCADE"), nullable=False
    )
    diagnosis_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    effort: Mapped[str] = mapped_column(String(10), nullable=False)
    impact: Mapped[str] = mapped_column(String(10), nullable=False)
    code_snippet: Mapped[str | None] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    effort_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    session: Mapped[DiagnosisSessionORM] = relationship("DiagnosisSessionORM", back_populates="recommendations")


class PipelineConfigCacheORM(Base):
    __tablename__ = "pipeline_config_cache"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    db_type: Mapped[str | None] = mapped_column(String(50))
    embedding_provider: Mapped[str | None] = mapped_column(String(50))
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    chunking_strategy: Mapped[str | None] = mapped_column(String(50))
    chunk_size: Mapped[int | None] = mapped_column(Integer)
    top_k: Mapped[int | None] = mapped_column(Integer)


class CalibrationResultORM(Base):
    __tablename__ = "calibration_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    embedding_model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    p25_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    p50_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    p75_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    calibrated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
