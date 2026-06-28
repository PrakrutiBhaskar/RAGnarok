"""Unit tests for RetrievalDiagnosticEngine."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.core.retrieval_diagnostics import RetrievalDiagnosticEngine
from backend.core.bm25_engine import BM25Engine


CORPUS = [
    {"chunk_id": "c1", "text": "To reset your password go to Settings > Security.", "metadata": {}},
    {"chunk_id": "c2", "text": "Annual subscriptions get a full refund within 30 days.", "metadata": {}},
    {"chunk_id": "c3", "text": "API rate limits: 100 calls per day for free tier.", "metadata": {}},
]


def make_engine(retrieved_chunks=None, embed_vec=None):
    retriever = AsyncMock()
    retriever.retrieve.return_value = retrieved_chunks or []
    retriever.get_corpus_chunks.return_value = CORPUS
    retriever.provider_name = "chroma"

    embedder = AsyncMock()
    embedder.embed_query.return_value = embed_vec or [0.1] * 384
    embedder.model_id = "all-MiniLM-L6-v2"
    embedder.provider_name = "huggingface"

    bm25 = BM25Engine()
    bm25.index(CORPUS)

    return RetrievalDiagnosticEngine(
        retriever=retriever,
        embedder=embedder,
        bm25_engine=bm25,
        top_k=3,
    )


class TestRetrievalDiagnosticEngine:
    async def test_no_chunks_returns_retrieval_fail(self):
        engine = make_engine(retrieved_chunks=[])
        result = await engine.diagnose("reset password", expected_answer="Settings > Security")
        assert result.verdict in ("RETRIEVAL_FAIL", "DATA_MISSING", "UNKNOWN")

    async def test_relevant_chunks_returns_retrieval_ok(self):
        # High similarity scores → retrieval OK
        engine = make_engine(retrieved_chunks=[
            {"chunk_id": "c1", "text": "Reset password via Settings.", "score": 0.85, "metadata": {}},
            {"chunk_id": "c2", "text": "Security settings available.", "score": 0.80, "metadata": {}},
            {"chunk_id": "c3", "text": "Password reset email sent.", "score": 0.78, "metadata": {}},
        ])
        result = await engine.diagnose("reset password")
        assert result.verdict in ("RETRIEVAL_OK", "RETRIEVAL_PARTIAL")

    async def test_low_similarity_returns_retrieval_fail(self):
        engine = make_engine(retrieved_chunks=[
            {"chunk_id": "c1", "text": "Unrelated content.", "score": 0.10, "metadata": {}},
            {"chunk_id": "c2", "text": "More unrelated content.", "score": 0.12, "metadata": {}},
        ])
        result = await engine.diagnose("reset password")
        assert result.verdict == "RETRIEVAL_FAIL"

    async def test_oracle_chunks_populated(self):
        engine = make_engine()
        result = await engine.diagnose("password reset")
        # BM25 should find relevant oracle chunks
        assert len(result.oracle_chunks) > 0

    async def test_answer_in_corpus_true(self):
        engine = make_engine()
        result = await engine.diagnose(
            "reset password",
            expected_answer="reset your password Settings Security",
        )
        assert result.expected_answer_in_corpus is True

    async def test_answer_not_in_corpus(self):
        engine = make_engine()
        result = await engine.diagnose(
            "quantum physics neutron stars",
            expected_answer="quantum entanglement superposition",
        )
        assert result.expected_answer_in_corpus is False

    async def test_evidence_contains_thresholds(self):
        engine = make_engine()
        result = await engine.diagnose("test query")
        assert "thresholds" in result.evidence
        assert "p50" in result.evidence["thresholds"]

    async def test_embedding_failure_returns_unknown(self):
        from backend.adapters.base import AdapterUnavailableError
        retriever = AsyncMock()
        embedder = AsyncMock()
        embedder.embed_query.side_effect = AdapterUnavailableError("test", "embed", "timeout")
        embedder.model_id = "all-MiniLM-L6-v2"
        bm25 = BM25Engine()
        bm25.index(CORPUS)
        engine = RetrievalDiagnosticEngine(retriever, embedder, bm25, top_k=3)
        result = await engine.diagnose("test query")
        assert result.verdict == "UNKNOWN"
        assert result.fallback_mode is True

    async def test_max_cosine_computed(self):
        engine = make_engine(retrieved_chunks=[
            {"chunk_id": "c1", "text": "Reset password.", "score": 0.72, "metadata": {}},
            {"chunk_id": "c2", "text": "Security settings.", "score": 0.65, "metadata": {}},
        ])
        result = await engine.diagnose("password reset")
        assert result.max_cosine_similarity == pytest.approx(0.72)
        assert result.avg_cosine_similarity == pytest.approx(0.685)