"""
Retrieval Diagnostic Engine.
Determines whether the retrieval layer is the source of failure for a given query.

Decision logic:
  - Re-runs retrieval via the adapter
  - Scores retrieved chunks using cosine similarity + BM25
  - Checks whether expected answer is in corpus (data quality signal)
  - Produces a RetrievalVerdict with evidence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.adapters.base import AdapterUnavailableError, EmbeddingAdapter, RetrieverAdapter
from backend.core.bm25_engine import BM25Engine
from backend.core.similarity_scorer import SimilarityScorer
from backend.models.session import ChunkEvidence, RetrievalVerdict

logger = logging.getLogger(__name__)


@dataclass
class RetrievalDiagnosisResult:
    """Output of the retrieval diagnostic for one query."""

    verdict: RetrievalVerdict
    retrieved_chunks: list[ChunkEvidence] = field(default_factory=list)
    oracle_chunks: list[ChunkEvidence] = field(default_factory=list)
    max_cosine_similarity: float | None = None
    avg_cosine_similarity: float | None = None
    bm25_score: float | None = None
    expected_answer_in_corpus: bool | None = None
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    fallback_mode: bool = False   # True when vector DB was unreachable


class RetrievalDiagnosticEngine:
    """
    Diagnoses the retrieval layer of a RAG pipeline.

    Instantiate once per session; call `diagnose()` for each query.
    """

    def __init__(
        self,
        retriever: RetrieverAdapter,
        embedder: EmbeddingAdapter,
        bm25_engine: BM25Engine,
        top_k: int = 5,
        score_threshold: float | None = None,
    ) -> None:
        self._retriever = retriever
        self._embedder = embedder
        self._bm25 = bm25_engine
        self._top_k = top_k
        self._score_threshold = score_threshold
        self._scorer = SimilarityScorer(model_id=embedder.model_id)

    async def diagnose(
        self,
        query: str,
        expected_answer: str | None = None,
        redact_pii: bool = False,
    ) -> RetrievalDiagnosisResult:
        """
        Run retrieval diagnostics for a single query.

        Args:
            query: The failing query text.
            expected_answer: Ground truth answer (supervised mode).
            redact_pii: If True, apply PII redaction before external calls.
        """
        # Step 1: Embed the query
        try:
            query_embedding = await self._embedder.embed_query(query)
        except AdapterUnavailableError as e:
            logger.error("RetrievalDiagnosticEngine: embedding failed: %s", e)
            return RetrievalDiagnosisResult(
                verdict="UNKNOWN",
                evidence={"embedding_error": str(e)},
                fallback_mode=True,
            )

        # Step 2: Retrieve from vector DB
        raw_chunks: list[dict[str, Any]] = []
        fallback_mode = False
        try:
            raw_chunks = await self._retriever.retrieve(
                query_embedding=query_embedding,
                top_k=self._top_k,
                score_threshold=self._score_threshold,
            )
        except AdapterUnavailableError as e:
            logger.warning(
                "RetrievalDiagnosticEngine: vector DB unreachable — falling back to static analysis: %s", e
            )
            fallback_mode = True

        # Step 3: BM25 oracle retrieval (ALWAYS from BM25, never from vector DB)
        oracle_raw = self._bm25.retrieve(query, top_k=self._top_k)
        oracle_chunks = [
            ChunkEvidence(
                chunk_id=r.chunk_id,
                text=r.text,
                bm25_score=r.score,
                source="bm25_oracle",
                metadata=r.metadata,
            )
            for r in oracle_raw
        ]
        bm25_top_score = oracle_raw[0].score if oracle_raw else None

        # Step 4: Score retrieved chunks
        retrieved_chunks = [
            ChunkEvidence(
                chunk_id=c.get("chunk_id", f"chunk_{i}"),
                text=c.get("text", ""),
                cosine_similarity=c.get("score"),
                source="vector_db",
                metadata=c.get("metadata", {}),
            )
            for i, c in enumerate(raw_chunks)
        ]

        max_cos, avg_cos = self._scorer.score_from_retrieved(raw_chunks)
        any_relevant = self._scorer.any_relevant(raw_chunks) if raw_chunks else False
        relevance_ratio = self._scorer.relevance_ratio(raw_chunks) if raw_chunks else 0.0

        # Step 5: Check if answer is in corpus (data quality signal)
        answer_in_corpus: bool | None = None
        if expected_answer and self._bm25.is_indexed:
            answer_in_corpus = self._bm25.is_answer_in_corpus(expected_answer)

        # Step 6: Classify retrieval verdict
        verdict, confidence, evidence = self._classify(
            raw_chunks=raw_chunks,
            any_relevant=any_relevant,
            relevance_ratio=relevance_ratio,
            max_cos=max_cos,
            avg_cos=avg_cos,
            bm25_top_score=bm25_top_score,
            oracle_found_results=len(oracle_raw) > 0,
            answer_in_corpus=answer_in_corpus,
            fallback_mode=fallback_mode,
        )

        return RetrievalDiagnosisResult(
            verdict=verdict,
            retrieved_chunks=retrieved_chunks,
            oracle_chunks=oracle_chunks,
            max_cosine_similarity=max_cos,
            avg_cosine_similarity=avg_cos,
            bm25_score=bm25_top_score,
            expected_answer_in_corpus=answer_in_corpus,
            confidence=confidence,
            evidence=evidence,
            fallback_mode=fallback_mode,
        )

    def _classify(
        self,
        raw_chunks: list[dict],
        any_relevant: bool,
        relevance_ratio: float,
        max_cos: float | None,
        avg_cos: float | None,
        bm25_top_score: float | None,
        oracle_found_results: bool,
        answer_in_corpus: bool | None,
        fallback_mode: bool,
    ) -> tuple[RetrievalVerdict, float, dict[str, Any]]:
        """Decision tree for retrieval verdict classification."""

        evidence: dict[str, Any] = {
            "chunk_count": len(raw_chunks),
            "any_relevant": any_relevant,
            "relevance_ratio": round(relevance_ratio, 3),
            "max_cosine_similarity": round(max_cos, 4) if max_cos is not None else None,
            "avg_cosine_similarity": round(avg_cos, 4) if avg_cos is not None else None,
            "bm25_top_score": round(bm25_top_score, 4) if bm25_top_score is not None else None,
            "oracle_found_results": oracle_found_results,
            "answer_in_corpus": answer_in_corpus,
            "fallback_mode": fallback_mode,
            "thresholds": {
                "p25": self._scorer.thresholds.p25,
                "p50": self._scorer.thresholds.p50,
                "p75": self._scorer.thresholds.p75,
                "model_id": self._scorer.thresholds.model_id,
            },
        }

        if fallback_mode and not raw_chunks:
            return "UNKNOWN", 0.3, evidence

        # No chunks returned at all
        if not raw_chunks:
            if answer_in_corpus is False:
                return "DATA_MISSING", 0.8, evidence
            return "RETRIEVAL_FAIL", 0.7, evidence

        # Data quality failure: answer not in corpus at all
        if answer_in_corpus is False and oracle_found_results is False:
            evidence["diagnosis_reason"] = "expected_answer_not_in_corpus"
            return "DATA_MISSING", 0.85, evidence

        # Retrieval failure: chunks returned but none are relevant
        if not any_relevant:
            confidence = 0.75 + (0.1 if bm25_top_score and bm25_top_score > 5.0 else 0.0)
            evidence["diagnosis_reason"] = "no_relevant_chunks_retrieved"
            return "RETRIEVAL_FAIL", min(confidence, 0.9), evidence

        # Partial retrieval: some relevant chunks but low ratio
        if relevance_ratio < 0.5:
            evidence["diagnosis_reason"] = "low_relevance_ratio"
            return "RETRIEVAL_PARTIAL", 0.65, evidence

        # Retrieval OK: majority of chunks are relevant
        evidence["diagnosis_reason"] = "sufficient_relevant_chunks"
        confidence = 0.7 + (0.2 if relevance_ratio > 0.75 else 0.0)
        return "RETRIEVAL_OK", min(confidence, 0.9), evidence
