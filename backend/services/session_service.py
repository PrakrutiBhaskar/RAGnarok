"""
Session service — orchestrates the full diagnostic pipeline for a session.
Creates session records, dispatches per-query diagnosis, aggregates results.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.adapters.base import AdapterError
from backend.core.bm25_engine import BM25Engine
from backend.core.compound_classifier import CompoundClassifier
from backend.core.generation_diagnostics import GenerationDiagnosticEngine
from backend.core.recommendation_engine import RecommendationEngine
from backend.core.retrieval_diagnostics import RetrievalDiagnosticEngine
from backend.db.orm_models import DiagnosisSessionORM, QueryDiagnosisORM, RecommendationORM
from backend.models.config import PipelineConfig, QueryBatch
from backend.models.session import (
    DiagnosisSession,
    QueryDiagnosisResult,
    SessionListItem,
    SessionStatusResponse,
)
from backend.security.secret_scrubber import scrub_dict, scrub_error_message

logger = logging.getLogger(__name__)


class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Factory: build adapters from config ──────────────────────────────────

    def _build_retriever(self, config: PipelineConfig):
        from backend.adapters.retrievers.chroma_adapter import ChromaAdapter
        provider = config.vector_db.provider
        if provider == "chroma":
            return ChromaAdapter(config.vector_db)
        # TODO: add Pinecone, Qdrant
        raise ValueError(f"Unsupported vector DB provider: {provider}")

    def _build_embedder(self, config: PipelineConfig):
        provider = config.embedding.provider
        if provider == "openai":
            from backend.adapters.embeddings.openai_embed import OpenAIEmbeddingAdapter
            return OpenAIEmbeddingAdapter(config.embedding)
        if provider == "huggingface":
            from backend.adapters.embeddings.huggingface_embed import HuggingFaceEmbeddingAdapter
            return HuggingFaceEmbeddingAdapter(config.embedding)
        raise ValueError(f"Unsupported embedding provider: {provider}")

    def _build_llm(self, config: PipelineConfig):
        provider = config.llm.provider
        if provider == "openai":
            from backend.adapters.llms.openai_llm import OpenAILLMAdapter
            return OpenAILLMAdapter(config.llm)
        if provider == "groq":
            from backend.adapters.llms.groq_llm import GroqLLMAdapter
            return GroqLLMAdapter(config.llm)
        raise ValueError(f"Unsupported LLM provider: {provider}")

    # ── Create session record ─────────────────────────────────────────────────

    async def create_session(
        self,
        pipeline_config: PipelineConfig,
        query_batch: QueryBatch,
        redact_pii: bool = False,
    ) -> DiagnosisSessionORM:
        config_snapshot = scrub_dict(pipeline_config.model_dump())

        orm = DiagnosisSessionORM(
            id=str(uuid4()),
            pipeline_config_hash=pipeline_config.fingerprint(),
            pipeline_config_snapshot=config_snapshot,
            query_count=len(query_batch.queries),
            status="pending",
            mode="supervised" if query_batch.is_supervised else "unsupervised",
            db_type=pipeline_config.vector_db.provider,
            embedding_provider=pipeline_config.embedding.provider,
            llm_provider=pipeline_config.llm.provider,
            chunking_strategy=pipeline_config.chunking.strategy,
            chunk_size=pipeline_config.chunking.chunk_size,
            top_k=pipeline_config.retrieval.top_k,
        )
        self._db.add(orm)
        await self._db.commit()
        await self._db.refresh(orm)
        logger.info("Created session %s (%d queries)", orm.id, orm.query_count)
        return orm

    # ── Main diagnosis orchestration ─────────────────────────────────────────

    async def run_diagnosis(
        self,
        session_id: str,
        pipeline_config: PipelineConfig,
        query_batch: QueryBatch,
        redact_pii: bool = False,
    ) -> None:
        """
        Full diagnostic pipeline — runs in background task.
        Updates session status and writes per-query results to DB.
        """
        start_time = time.monotonic()

        # Mark running
        await self._update_session_status(session_id, "running")

        try:
            # Build adapters
            retriever = self._build_retriever(pipeline_config)
            embedder = self._build_embedder(pipeline_config)
            llm = self._build_llm(pipeline_config)

            # Build BM25 oracle index (once per session)
            bm25_engine = BM25Engine(max_chunks=100_000)
            try:
                corpus_chunks = await retriever.get_corpus_chunks(limit=100_000)
                bm25_engine.index(corpus_chunks)
                logger.info(
                    "Session %s: BM25 indexed %d chunks",
                    session_id, bm25_engine.corpus_size,
                )
            except AdapterError as e:
                logger.warning(
                    "Session %s: failed to build BM25 index: %s — "
                    "generation diagnostics and data quality checks will be degraded.",
                    session_id, scrub_error_message(e),
                )

            # Build diagnostic engines
            retrieval_engine = RetrievalDiagnosticEngine(
                retriever=retriever,
                embedder=embedder,
                bm25_engine=bm25_engine,
                top_k=pipeline_config.retrieval.top_k,
                score_threshold=pipeline_config.retrieval.score_threshold,
            )
            generation_engine = GenerationDiagnosticEngine(
                llm=llm,
                prompt_config=pipeline_config.prompt,
            )
            classifier = CompoundClassifier()

            # Per-query diagnosis loop
            query_diagnoses: list[QueryDiagnosisResult] = []
            failed_queries = 0

            for i, query_obj in enumerate(query_batch.queries):
                try:
                    qd = await self._diagnose_query(
                        session_id=session_id,
                        query_index=i,
                        total=len(query_batch.queries),
                        query_obj=query_obj,
                        retrieval_engine=retrieval_engine,
                        generation_engine=generation_engine,
                        classifier=classifier,
                        redact_pii=redact_pii,
                    )
                    query_diagnoses.append(qd)
                    await self._save_query_diagnosis(session_id, qd)
                    self._publish_progress(session_id, i, len(query_batch.queries), qd)

                except Exception as e:
                    logger.error(
                        "Session %s: query %d failed: %s",
                        session_id, i, scrub_error_message(e),
                    )
                    failed_queries += 1

            # Aggregate and save recommendations
            rec_engine = RecommendationEngine()
            failure_dist = self._compute_failure_distribution(query_diagnoses)
            dominant = self._dominant_failure(failure_dist)

            from uuid import UUID
            recommendations = rec_engine.generate(
                session_id=UUID(session_id),
                dominant_failure=dominant,
                failure_distribution=failure_dist,
                session_evidence={
                    "query_count": len(query_batch.queries),
                    "failed_queries": failed_queries,
                    "bm25_corpus_size": bm25_engine.corpus_size,
                },
            )

            for rec in recommendations:
                rec_orm = RecommendationORM(
                    id=str(rec.id),
                    session_id=session_id,
                    diagnosis_type=rec.diagnosis_type,
                    title=rec.title,
                    description=rec.description,
                    effort=rec.effort,
                    impact=rec.impact,
                    code_snippet=rec.code_snippet,
                    rank=rec.rank,
                    impact_score=rec.impact_score,
                    effort_score=rec.effort_score,
                )
                self._db.add(rec_orm)

            # Compute overall confidence
            overall_confidence = (
                sum(qd.confidence_score for qd in query_diagnoses) / len(query_diagnoses)
                if query_diagnoses else 0.0
            )

            final_status = "complete" if failed_queries == 0 else "partial"
            await self._update_session_status(
                session_id,
                final_status,
                overall_confidence=overall_confidence,
            )

            elapsed = time.monotonic() - start_time
            logger.info(
                "Session %s complete in %.1fs — %d queries, dominant_failure=%s, confidence=%.2f",
                session_id, elapsed, len(query_diagnoses), dominant, overall_confidence,
            )
            self._publish_complete(session_id, len(query_diagnoses))

        except Exception as e:
            logger.error("Session %s failed: %s", session_id, scrub_error_message(e))
            await self._update_session_status(session_id, "failed")
            self._publish_error(session_id, str(e))

    async def _diagnose_query(
        self,
        session_id: str,
        query_index: int,
        total: int,
        query_obj,
        retrieval_engine: RetrievalDiagnosticEngine,
        generation_engine: GenerationDiagnosticEngine,
        classifier: CompoundClassifier,
        redact_pii: bool,
    ) -> QueryDiagnosisResult:
        """Run retrieval + generation diagnostics for a single query."""
        from uuid import UUID

        # Retrieval diagnosis
        r_result = await retrieval_engine.diagnose(
            query=query_obj.query,
            expected_answer=query_obj.expected_answer,
            redact_pii=redact_pii,
        )

        # Generation diagnosis (oracle injection)
        # Re-retrieve oracle chunks directly from BM25 engine using the typed result
        from backend.core.bm25_engine import BM25Result
        oracle_bm25_chunks = [
            BM25Result(
                chunk_id=c.chunk_id,
                text=c.text,
                score=c.bm25_score or 0.0,
                metadata=c.metadata,
            )
            for c in r_result.oracle_chunks
        ]
        g_result = await generation_engine.diagnose(
            query=query_obj.query,
            oracle_chunks=oracle_bm25_chunks,
            actual_answer=query_obj.actual_answer,
            expected_answer=query_obj.expected_answer,
            redact_pii=redact_pii,
        )

        # Compound classification
        classification = classifier.classify(
            retrieval_verdict=r_result.verdict,
            generation_verdict=g_result.verdict,
            retrieval_confidence=r_result.confidence,
            generation_confidence=g_result.confidence,
            retrieval_evidence=r_result.evidence,
            generation_evidence=g_result.evidence,
        )

        return QueryDiagnosisResult(
            session_id=UUID(session_id),
            query_text=query_obj.query,
            expected_answer=query_obj.expected_answer,
            actual_answer=query_obj.actual_answer,
            retrieved_chunks=r_result.retrieved_chunks,
            oracle_chunks=r_result.oracle_chunks,
            retrieval_verdict=r_result.verdict,
            generation_verdict=g_result.verdict,
            final_diagnosis=classification.final_diagnosis,
            confidence_score=classification.confidence_score,
            max_cosine_similarity=r_result.max_cosine_similarity,
            avg_cosine_similarity=r_result.avg_cosine_similarity,
            bm25_score=r_result.bm25_score,
            expected_answer_in_corpus=r_result.expected_answer_in_corpus,
            evidence=classification.evidence,
        )

    async def _save_query_diagnosis(self, session_id: str, qd: QueryDiagnosisResult) -> None:
        orm = QueryDiagnosisORM(
            id=str(qd.id),
            session_id=session_id,
            query_text=qd.query_text,
            expected_answer=qd.expected_answer,
            actual_answer=qd.actual_answer,
            retrieved_chunks=[c.model_dump() for c in qd.retrieved_chunks],
            oracle_chunks=[c.model_dump() for c in qd.oracle_chunks],
            retrieval_verdict=qd.retrieval_verdict,
            generation_verdict=qd.generation_verdict,
            final_diagnosis=qd.final_diagnosis,
            confidence_score=qd.confidence_score,
            max_cosine_similarity=qd.max_cosine_similarity,
            avg_cosine_similarity=qd.avg_cosine_similarity,
            bm25_score=qd.bm25_score,
            expected_answer_in_corpus=qd.expected_answer_in_corpus,
            evidence=qd.evidence,
        )
        self._db.add(orm)
        await self._db.commit()

    async def _update_session_status(
        self,
        session_id: str,
        status: str,
        overall_confidence: float | None = None,
    ) -> None:
        result = await self._db.execute(
            select(DiagnosisSessionORM).where(DiagnosisSessionORM.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.status = status
            session.updated_at = datetime.utcnow()
            if overall_confidence is not None:
                session.overall_confidence = overall_confidence
            await self._db.commit()

    def _compute_failure_distribution(
        self, diagnoses: list[QueryDiagnosisResult]
    ) -> dict[str, int]:
        dist: dict[str, int] = {}
        for qd in diagnoses:
            dist[qd.final_diagnosis] = dist.get(qd.final_diagnosis, 0) + 1
        return dist

    def _dominant_failure(self, dist: dict[str, int]):
        if not dist:
            return None
        return max(dist, key=lambda k: dist[k])

    # ── SSE publishing helpers ────────────────────────────────────────────────

    def _publish_progress(self, session_id, i, total, qd):
        try:
            from backend.api.routes.stream import publish_event
            from backend.models.report import StreamEvent
            publish_event(session_id, StreamEvent(
                event="query_complete",
                session_id=session_id,
                query_index=i,
                total_queries=total,
                query_text=qd.query_text[:80],
                diagnosis=qd.final_diagnosis,
                confidence=qd.confidence_score,
            ))
        except Exception:
            pass

    def _publish_complete(self, session_id, total):
        try:
            from backend.api.routes.stream import publish_event
            from backend.models.report import StreamEvent
            publish_event(session_id, StreamEvent(
                event="session_complete",
                session_id=session_id,
                total_queries=total,
            ))
        except Exception:
            pass

    def _publish_error(self, session_id, error):
        try:
            from backend.api.routes.stream import publish_event
            from backend.models.report import StreamEvent
            publish_event(session_id, StreamEvent(
                event="error",
                session_id=session_id,
                error=error,
            ))
        except Exception:
            pass

    # ── Query methods ─────────────────────────────────────────────────────────

    async def get_session(self, session_id: str) -> SessionStatusResponse | None:
        result = await self._db.execute(
            select(DiagnosisSessionORM).where(DiagnosisSessionORM.id == session_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None

        # Count completed queries AND compute failure distribution from DB
        q_result = await self._db.execute(
            select(QueryDiagnosisORM).where(QueryDiagnosisORM.session_id == session_id)
        )
        query_rows = q_result.scalars().all()
        completed = len(query_rows)

        failure_distribution: dict[str, int] = {}
        for row in query_rows:
            diag = row.final_diagnosis
            failure_distribution[diag] = failure_distribution.get(diag, 0) + 1

        return SessionStatusResponse(
            id=orm.id,
            status=orm.status,
            mode=orm.mode,
            query_count=orm.query_count,
            completed_queries=completed,
            overall_confidence=orm.overall_confidence,
            failure_distribution=failure_distribution,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def get_session_full(self, session_id: str) -> DiagnosisSessionORM | None:
        result = await self._db.execute(
            select(DiagnosisSessionORM)
            .options(
                selectinload(DiagnosisSessionORM.query_diagnoses),
                selectinload(DiagnosisSessionORM.recommendations),
            )
            .where(DiagnosisSessionORM.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_sessions(self, limit: int = 20, offset: int = 0) -> list[SessionListItem]:
        result = await self._db.execute(
            select(DiagnosisSessionORM)
            .order_by(DiagnosisSessionORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        sessions = result.scalars().all()
        items = []
        for s in sessions:
            # Compute dominant failure from query diagnoses
            from sqlalchemy import func as sqlfunc
            dist_result = await self._db.execute(
                select(QueryDiagnosisORM.final_diagnosis, sqlfunc.count().label("cnt"))
                .where(QueryDiagnosisORM.session_id == s.id)
                .group_by(QueryDiagnosisORM.final_diagnosis)
                .order_by(sqlfunc.count().desc())
                .limit(1)
            )
            top = dist_result.first()
            dominant = top[0] if top else None
            items.append(SessionListItem(
                id=s.id,
                created_at=s.created_at,
                status=s.status,
                mode=s.mode,
                query_count=s.query_count,
                db_type=s.db_type,
                embedding_provider=s.embedding_provider,
                llm_provider=s.llm_provider,
                dominant_failure=dominant,
                overall_confidence=s.overall_confidence,
            ))
        return items

    async def delete_session(self, session_id: str) -> bool:
        result = await self._db.execute(
            select(DiagnosisSessionORM).where(DiagnosisSessionORM.id == session_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return False
        await self._db.delete(orm)
        await self._db.commit()
        return True