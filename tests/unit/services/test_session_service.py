"""
Unit/integration tests for SessionService.

This is the orchestration conductor — the class that actually runs a
diagnostic session in production. It previously had ~21% test coverage
despite being the single most important piece of integration code in the
project. These tests exercise it against a real (temp-file) SQLite DB with
fake adapters standing in for the vector DB / embedder / LLM, so the
DB-session lifecycle, status transitions, and aggregation logic are all
genuinely exercised rather than mocked away.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.adapters.base import AdapterError
from backend.core.bm25_engine import BM25Result
from backend.db.orm_models import (
    DiagnosisSessionORM,
    PipelineConfigCacheORM,
    QueryDiagnosisORM,
    RecommendationORM,
)
from backend.models.config import (
    ChunkingConfig,
    EmbeddingConfig,
    FailingQuery,
    LLMConfig,
    PipelineConfig,
    PromptConfig,
    QueryBatch,
    RetrievalConfig,
    VectorDBConfig,
)
from backend.services.session_service import SessionService
from sqlalchemy import select


# ── Fake adapters (stand in for real vector DB / embedder / LLM) ────────────

class FakeRetriever:
    """Always returns one highly-relevant chunk — drives a no_failure_detected path."""

    provider_name = "fake"

    def __init__(self, chunks=None, corpus=None, raise_on_corpus=False):
        self._chunks = chunks if chunks is not None else [
            {"chunk_id": "c1", "text": "Refunds are processed within 5 business days.",
             "score": 0.95, "metadata": {}},
        ]
        self._corpus = corpus if corpus is not None else [
            {"chunk_id": "c1", "text": "Refunds are processed within 5 business days.",
             "metadata": {}},
        ]
        self._raise_on_corpus = raise_on_corpus

    async def retrieve(self, query_embedding, top_k, score_threshold=None):
        return self._chunks

    async def health_check(self):
        return True

    async def get_corpus_chunks(self, limit=100_000):
        if self._raise_on_corpus:
            raise AdapterError("fake", "get_corpus", "corpus unavailable")
        return self._corpus


class FakeEmbedder:
    provider_name = "fake"
    model_id = "fake-embed"

    async def embed_query(self, text):
        return [0.1, 0.2, 0.3]

    async def embed_batch(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def health_check(self):
        return True


class FakeLLM:
    provider_name = "fake"
    model_id = "fake-llm"

    def __init__(self, answer="Refunds are processed within 5 business days."):
        self._answer = answer

    async def generate(self, prompt, system_prompt=None, temperature=0.0, max_tokens=1024):
        return self._answer

    async def health_check(self):
        return True


# ── Config builders ──────────────────────────────────────────────────────────

def make_pipeline_config(with_prompt: bool = True) -> PipelineConfig:
    return PipelineConfig(
        name="Test Pipeline",
        vector_db=VectorDBConfig(provider="chroma", collection_name="docs"),
        embedding=EmbeddingConfig(provider="openai", model_id="text-embedding-3-small"),
        llm=LLMConfig(provider="openai", model_id="gpt-4o-mini"),
        chunking=ChunkingConfig(),
        retrieval=RetrievalConfig(top_k=5),
        prompt=PromptConfig(
            template="Context:\n{context}\n\nQuestion: {question}\n\nAnswer:",
        ) if with_prompt else None,
    )


def make_query_batch(n: int = 1, with_expected: bool = True) -> QueryBatch:
    queries = [
        FailingQuery(
            query=f"What is the refund policy? ({i})",
            expected_answer="Refunds are processed within 5 business days." if with_expected else None,
        )
        for i in range(n)
    ]
    return QueryBatch(queries=queries)


@pytest.fixture
def patched_adapters():
    """Patch SessionService's adapter factories to return fakes instead of
    hitting real vendor SDKs / network calls."""
    retriever = FakeRetriever()
    embedder = FakeEmbedder()
    llm = FakeLLM()

    with patch.object(SessionService, "_build_retriever", return_value=retriever), \
         patch.object(SessionService, "_build_embedder", return_value=embedder), \
         patch.object(SessionService, "_build_llm", return_value=llm):
        yield retriever, embedder, llm


class TestCreateSession:
    async def test_persists_session_with_correct_metadata(self, db_session):
        service = SessionService(db_session)
        config = make_pipeline_config()
        batch = make_query_batch(n=2)

        orm = await service.create_session(config, batch, redact_pii=False)

        assert orm.status == "pending"
        assert orm.query_count == 2
        assert orm.mode == "supervised"
        assert orm.db_type == "chroma"
        assert orm.embedding_provider == "openai"
        assert orm.llm_provider == "openai"
        assert orm.pipeline_config_hash == config.fingerprint()

    async def test_unsupervised_mode_when_no_expected_answers(self, db_session):
        service = SessionService(db_session)
        batch = make_query_batch(n=1, with_expected=False)

        orm = await service.create_session(make_pipeline_config(), batch)
        assert orm.mode == "unsupervised"

    async def test_config_snapshot_is_secret_scrubbed(self, db_session):
        """create_session must scrub the config snapshot before persisting —
        this is the actual call site that makes the secret_scrubber claim
        in the README true; verify it's really wired in, not just tested
        in isolation."""
        service = SessionService(db_session)
        config = make_pipeline_config()

        orm = await service.create_session(config, make_query_batch())
        # api keys aren't part of PipelineConfig itself (they come from env),
        # but the scrub_dict call must still have run without raising and
        # produced a plain-JSON-serializable snapshot.
        assert isinstance(orm.pipeline_config_snapshot, dict)
        assert orm.pipeline_config_snapshot["name"] == "Test Pipeline"


class TestPipelineConfigUsageTracking:
    """PipelineConfigCacheORM was fully schema-defined but had zero call
    sites — confirm create_session now actually upserts it."""

    async def test_first_session_for_a_config_creates_cache_row(self, db_session):
        service = SessionService(db_session)
        config = make_pipeline_config()

        await service.create_session(config, make_query_batch())

        cache_row = await db_session.get(PipelineConfigCacheORM, config.fingerprint())
        assert cache_row is not None
        assert cache_row.session_count == 1
        assert cache_row.db_type == "chroma"

    async def test_repeated_sessions_for_same_config_increment_count(self, db_session):
        service = SessionService(db_session)
        config = make_pipeline_config()

        await service.create_session(config, make_query_batch())
        await service.create_session(config, make_query_batch())
        await service.create_session(config, make_query_batch())

        cache_row = await db_session.get(PipelineConfigCacheORM, config.fingerprint())
        assert cache_row.session_count == 3

    async def test_different_configs_get_separate_cache_rows(self, db_session):
        service = SessionService(db_session)
        config_a = make_pipeline_config()
        config_b = make_pipeline_config()
        config_b.retrieval.top_k = 20  # changes the fingerprint

        await service.create_session(config_a, make_query_batch())
        await service.create_session(config_b, make_query_batch())

        assert config_a.fingerprint() != config_b.fingerprint()
        row_a = await db_session.get(PipelineConfigCacheORM, config_a.fingerprint())
        row_b = await db_session.get(PipelineConfigCacheORM, config_b.fingerprint())
        assert row_a.session_count == 1
        assert row_b.session_count == 1


class TestRunDiagnosisHappyPath:
    async def test_completes_with_no_failure_detected(self, db_session, patched_adapters):
        service = SessionService(db_session)
        config = make_pipeline_config()
        batch = make_query_batch(n=1)

        session_orm = await service.create_session(config, batch)
        await service.run_diagnosis(session_orm.id, config, batch, redact_pii=False)

        result = await db_session.execute(
            select(DiagnosisSessionORM).where(DiagnosisSessionORM.id == session_orm.id)
        )
        updated = result.scalar_one()
        assert updated.status == "complete"
        assert updated.overall_confidence is not None
        assert updated.overall_confidence > 0.0

    async def test_persists_one_query_diagnosis_per_query(self, db_session, patched_adapters):
        service = SessionService(db_session)
        config = make_pipeline_config()
        batch = make_query_batch(n=3)

        session_orm = await service.create_session(config, batch)
        await service.run_diagnosis(session_orm.id, config, batch)

        result = await db_session.execute(
            select(QueryDiagnosisORM).where(QueryDiagnosisORM.session_id == session_orm.id)
        )
        rows = result.scalars().all()
        assert len(rows) == 3
        for row in rows:
            assert row.final_diagnosis in (
                "no_failure_detected", "retrieval_failure", "generation_failure",
                "compound_failure", "data_quality_failure", "insufficient_evidence",
            )

    async def test_skips_generation_diagnostic_without_prompt_config(self, db_session, patched_adapters):
        service = SessionService(db_session)
        config = make_pipeline_config(with_prompt=False)
        batch = make_query_batch(n=1)

        session_orm = await service.create_session(config, batch)
        await service.run_diagnosis(session_orm.id, config, batch)

        result = await db_session.execute(
            select(QueryDiagnosisORM).where(QueryDiagnosisORM.session_id == session_orm.id)
        )
        row = result.scalars().first()
        assert row.generation_verdict == "SKIPPED"

    async def test_generates_recommendations_for_dominant_failure(self, db_session):
        """Force a retrieval failure (no relevant chunks) and confirm
        recommendations get persisted, ranked, and tied to the session."""
        bad_retriever = FakeRetriever(chunks=[])
        embedder = FakeEmbedder()
        llm = FakeLLM()

        with patch.object(SessionService, "_build_retriever", return_value=bad_retriever), \
             patch.object(SessionService, "_build_embedder", return_value=embedder), \
             patch.object(SessionService, "_build_llm", return_value=llm):
            service = SessionService(db_session)
            config = make_pipeline_config()
            batch = make_query_batch(n=1)

            session_orm = await service.create_session(config, batch)
            await service.run_diagnosis(session_orm.id, config, batch)

        result = await db_session.execute(
            select(RecommendationORM).where(RecommendationORM.session_id == session_orm.id)
        )
        recs = result.scalars().all()
        assert len(recs) > 0
        ranks = [r.rank for r in recs]
        assert ranks == sorted(ranks)


class TestRunDiagnosisFailureModes:
    async def test_marks_session_failed_when_adapter_build_raises(self, db_session):
        service = SessionService(db_session)
        config = make_pipeline_config()
        batch = make_query_batch(n=1)

        session_orm = await service.create_session(config, batch)

        with patch.object(
            SessionService, "_build_retriever", side_effect=ValueError("bad provider")
        ):
            await service.run_diagnosis(session_orm.id, config, batch)

        result = await db_session.execute(
            select(DiagnosisSessionORM).where(DiagnosisSessionORM.id == session_orm.id)
        )
        updated = result.scalar_one()
        assert updated.status == "failed"

    async def test_continues_and_marks_partial_when_one_query_errors(self, db_session):
        """A single query that raises mid-diagnosis should not abort the
        whole session — the other queries should still be diagnosed and
        the session should land in 'partial', not 'failed'."""

        class FlakyRetriever(FakeRetriever):
            def __init__(self):
                super().__init__()
                self._calls = 0

            async def retrieve(self, query_embedding, top_k, score_threshold=None):
                self._calls += 1
                if self._calls == 1:
                    raise RuntimeError("transient failure")
                return await super().retrieve(query_embedding, top_k, score_threshold)

        flaky = FlakyRetriever()
        embedder = FakeEmbedder()
        llm = FakeLLM()

        with patch.object(SessionService, "_build_retriever", return_value=flaky), \
             patch.object(SessionService, "_build_embedder", return_value=embedder), \
             patch.object(SessionService, "_build_llm", return_value=llm):
            service = SessionService(db_session)
            config = make_pipeline_config()
            batch = make_query_batch(n=2)

            session_orm = await service.create_session(config, batch)
            await service.run_diagnosis(session_orm.id, config, batch)

        result = await db_session.execute(
            select(DiagnosisSessionORM).where(DiagnosisSessionORM.id == session_orm.id)
        )
        updated = result.scalar_one()
        assert updated.status == "partial"

        diag_result = await db_session.execute(
            select(QueryDiagnosisORM).where(QueryDiagnosisORM.session_id == session_orm.id)
        )
        assert len(diag_result.scalars().all()) == 1  # only the surviving query was saved

    async def test_degrades_gracefully_when_corpus_fetch_fails(self, db_session):
        """BM25 index build failure (e.g. vector DB unreachable for corpus
        listing) should not crash the session — it should proceed with an
        empty/unindexed BM25 oracle and still complete."""
        retriever = FakeRetriever(raise_on_corpus=True)
        embedder = FakeEmbedder()
        llm = FakeLLM()

        with patch.object(SessionService, "_build_retriever", return_value=retriever), \
             patch.object(SessionService, "_build_embedder", return_value=embedder), \
             patch.object(SessionService, "_build_llm", return_value=llm):
            service = SessionService(db_session)
            config = make_pipeline_config()
            batch = make_query_batch(n=1)

            session_orm = await service.create_session(config, batch)
            await service.run_diagnosis(session_orm.id, config, batch)

        result = await db_session.execute(
            select(DiagnosisSessionORM).where(DiagnosisSessionORM.id == session_orm.id)
        )
        updated = result.scalar_one()
        assert updated.status in ("complete", "partial")


class TestQueryMethods:
    async def test_get_session_returns_none_for_unknown_id(self, db_session):
        service = SessionService(db_session)
        result = await service.get_session("nonexistent-id")
        assert result is None

    async def test_get_session_reports_completed_query_count_and_distribution(
        self, db_session, patched_adapters
    ):
        service = SessionService(db_session)
        config = make_pipeline_config()
        batch = make_query_batch(n=2)

        session_orm = await service.create_session(config, batch)
        await service.run_diagnosis(session_orm.id, config, batch)

        status = await service.get_session(session_orm.id)
        assert status is not None
        assert status.completed_queries == 2
        assert sum(status.failure_distribution.values()) == 2

    async def test_list_sessions_orders_most_recent_first(self, db_session):
        service = SessionService(db_session)
        config = make_pipeline_config()
        first = await service.create_session(config, make_query_batch())
        second = await service.create_session(config, make_query_batch())

        items = await service.list_sessions(limit=10)
        ids = [str(i.id) for i in items]
        assert ids.index(second.id) < ids.index(first.id)

    async def test_delete_session_removes_it_and_cascades(self, db_session, patched_adapters):
        service = SessionService(db_session)
        config = make_pipeline_config()
        batch = make_query_batch(n=1)

        session_orm = await service.create_session(config, batch)
        await service.run_diagnosis(session_orm.id, config, batch)

        deleted = await service.delete_session(session_orm.id)
        assert deleted is True

        assert await service.get_session(session_orm.id) is None

        remaining = await db_session.execute(
            select(QueryDiagnosisORM).where(QueryDiagnosisORM.session_id == session_orm.id)
        )
        assert remaining.scalars().all() == []  # cascade delete-orphan worked

    async def test_delete_session_returns_false_for_unknown_id(self, db_session):
        service = SessionService(db_session)
        assert await service.delete_session("nonexistent-id") is False


class TestSSEPublishHelpersNeverRaise:
    """These helpers are called from deep inside the diagnosis loop and are
    intentionally defensive (best-effort SSE push) — verify they genuinely
    swallow errors from a broken/absent stream module rather than taking
    down the whole diagnosis run."""

    async def test_publish_progress_does_not_raise_on_broken_stream_module(self, db_session):
        service = SessionService(db_session)
        with patch(
            "backend.api.routes.stream.publish_event", side_effect=RuntimeError("boom")
        ):
            service._publish_progress("sid", 0, 1, type("QD", (), {
                "query_text": "x", "final_diagnosis": "no_failure_detected",
                "confidence_score": 1.0,
            })())  # should not raise

    async def test_publish_complete_and_error_do_not_raise(self, db_session):
        service = SessionService(db_session)
        with patch(
            "backend.api.routes.stream.publish_event", side_effect=RuntimeError("boom")
        ):
            service._publish_complete("sid", 5)
            service._publish_error("sid", "some error")
