"""Unit tests for ReportService — building structured reports and rendering Markdown."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.db.orm_models import DiagnosisSessionORM, QueryDiagnosisORM, RecommendationORM
from backend.services.report_service import ReportService

SESSION_ID = str(uuid.uuid4())
NOW = datetime.now(timezone.utc).replace(tzinfo=None)


def make_session_orm(status="complete", overall_confidence=0.8, config_name="My Pipeline"):
    return DiagnosisSessionORM(
        id=SESSION_ID,
        pipeline_config_hash="abc123",
        pipeline_config_snapshot={"name": config_name},
        query_count=2,
        status=status,
        mode="supervised",
        overall_confidence=overall_confidence,
        db_type="chroma",
        embedding_provider="openai",
        llm_provider="openai",
        chunking_strategy="recursive",
        chunk_size=512,
        top_k=5,
        created_at=NOW,
        updated_at=NOW,
    )


def make_query_diagnosis_orm(session_id, final_diagnosis, confidence_score, idx=0):
    return QueryDiagnosisORM(
        id=str(uuid.uuid4()),
        session_id=session_id,
        query_text=f"Query {idx}",
        expected_answer="Some expected answer",
        actual_answer="Some actual answer",
        retrieved_chunks=[],
        oracle_chunks=[],
        retrieval_verdict="RETRIEVAL_OK",
        generation_verdict="GENERATION_OK",
        final_diagnosis=final_diagnosis,
        confidence_score=confidence_score,
        max_cosine_similarity=0.7,
        avg_cosine_similarity=0.6,
        bm25_score=3.2,
        expected_answer_in_corpus=True,
        evidence={"reason": "test"},
        created_at=NOW,
    )


def make_recommendation_orm(session_id, rank=1):
    return RecommendationORM(
        id=str(uuid.uuid4()),
        session_id=session_id,
        diagnosis_type="retrieval_failure",
        title="Increase top_k",
        description="Retrieve more chunks.",
        effort="low",
        impact="high",
        code_snippet="retrieval:\n  top_k: 10",
        rank=rank,
        impact_score=0.85,
        effort_score=0.1,
        created_at=NOW,
    )


class TestBuildReport:
    async def test_computes_dominant_failure_and_distribution(self, db_session):
        session = make_session_orm()
        session.query_diagnoses = [
            make_query_diagnosis_orm(session.id, "retrieval_failure", 0.9, 0),
            make_query_diagnosis_orm(session.id, "retrieval_failure", 0.8, 1),
            make_query_diagnosis_orm(session.id, "generation_failure", 0.7, 2),
        ]
        session.recommendations = []

        service = ReportService(db_session)
        report = await service.build_report(session)

        assert report.summary.total_queries == 3
        assert report.summary.dominant_failure == "retrieval_failure"
        assert report.summary.failure_distribution == {
            "retrieval_failure": 2,
            "generation_failure": 1,
        }
        assert report.pipeline_name == "My Pipeline"

    async def test_low_confidence_flag_and_count(self, db_session):
        session = make_session_orm()
        session.query_diagnoses = [
            make_query_diagnosis_orm(session.id, "retrieval_failure", 0.3, 0),  # low
            make_query_diagnosis_orm(session.id, "retrieval_failure", 0.9, 1),  # high
        ]
        session.recommendations = []

        service = ReportService(db_session)
        report = await service.build_report(session)

        assert report.summary.low_confidence_count == 1
        assert report.low_confidence_flag is True

    async def test_no_low_confidence_flag_when_all_confident(self, db_session):
        session = make_session_orm()
        session.query_diagnoses = [
            make_query_diagnosis_orm(session.id, "no_failure_detected", 0.9, 0),
        ]
        session.recommendations = []

        service = ReportService(db_session)
        report = await service.build_report(session)

        assert report.low_confidence_flag is False

    async def test_recommendations_sorted_by_rank(self, db_session):
        session = make_session_orm()
        session.query_diagnoses = [
            make_query_diagnosis_orm(session.id, "retrieval_failure", 0.9, 0),
        ]
        session.recommendations = [
            make_recommendation_orm(session.id, rank=2),
            make_recommendation_orm(session.id, rank=1),
        ]

        service = ReportService(db_session)
        report = await service.build_report(session)

        assert [r.rank for r in report.recommendations] == [1, 2]

    async def test_falls_back_to_session_id_prefix_when_no_config_name(self, db_session):
        session = make_session_orm(config_name=None)
        session.pipeline_config_snapshot = {}
        session.query_diagnoses = []
        session.recommendations = []

        service = ReportService(db_session)
        report = await service.build_report(session)

        assert report.pipeline_name.startswith("Session ")


class TestRenderMarkdown:
    async def test_markdown_contains_key_sections(self, db_session):
        session = make_session_orm()
        session.query_diagnoses = [
            make_query_diagnosis_orm(session.id, "retrieval_failure", 0.85, 0),
        ]
        session.recommendations = [make_recommendation_orm(session.id, rank=1)]

        service = ReportService(db_session)
        report = await service.build_report(session)
        md = service.render_markdown(report)

        assert "# RAG Debugger Report" in md
        assert "## Summary" in md
        assert "## Recommendations" in md
        assert "## Query Diagnoses" in md
        assert "Increase top_k" in md
        assert "```python" in md  # code snippet fenced

    async def test_markdown_flags_low_confidence_queries(self, db_session):
        session = make_session_orm()
        session.query_diagnoses = [
            make_query_diagnosis_orm(session.id, "insufficient_evidence", 0.2, 0),
        ]
        session.recommendations = []

        service = ReportService(db_session)
        report = await service.build_report(session)
        md = service.render_markdown(report)

        assert "Low confidence" in md

    async def test_markdown_handles_no_recommendations(self, db_session):
        session = make_session_orm()
        session.query_diagnoses = [
            make_query_diagnosis_orm(session.id, "no_failure_detected", 0.9, 0),
        ]
        session.recommendations = []

        service = ReportService(db_session)
        report = await service.build_report(session)
        md = service.render_markdown(report)

        assert "No recommendations generated" in md
