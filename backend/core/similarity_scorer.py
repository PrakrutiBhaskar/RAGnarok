"""
Similarity scorer — computes cosine similarity between query embedding and chunk embeddings.
Applies per-model thresholds via ThresholdCalibrator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from backend.core.threshold_calibrator import ThresholdCalibrator, ThresholdSet

logger = logging.getLogger(__name__)


@dataclass
class SimilarityScore:
    """Scored similarity between a query and a single chunk."""

    chunk_id: str
    cosine_similarity: float
    relevance_tier: str   # "high" | "medium" | "low"
    is_relevant: bool


class SimilarityScorer:
    """
    Scores retrieved chunks against calibrated per-model thresholds.
    Computes cosine similarity and classifies relevance.
    """

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id
        self._calibrator = ThresholdCalibrator()
        self._thresholds: ThresholdSet | None = None

    def _get_thresholds(self) -> ThresholdSet:
        if self._thresholds is None:
            self._thresholds = self._calibrator.get_thresholds(self._model_id)
        return self._thresholds

    def score(
        self,
        query_embedding: list[float],
        chunk_embeddings: list[tuple[str, list[float]]],
    ) -> list[SimilarityScore]:
        """
        Score a list of (chunk_id, embedding) pairs against a query embedding.

        Args:
            query_embedding: Embedding vector for the query.
            chunk_embeddings: List of (chunk_id, embedding) tuples.

        Returns:
            Sorted list of SimilarityScore, descending by cosine_similarity.
        """
        thresholds = self._get_thresholds()
        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)

        if q_norm == 0:
            logger.warning("SimilarityScorer: zero-norm query embedding — returning empty scores")
            return []

        q_unit = q_vec / q_norm
        scores: list[SimilarityScore] = []

        for chunk_id, embedding in chunk_embeddings:
            c_vec = np.array(embedding, dtype=np.float32)
            c_norm = np.linalg.norm(c_vec)

            if c_norm == 0:
                logger.debug("SimilarityScorer: zero-norm embedding for chunk '%s'", chunk_id)
                cosine_sim = 0.0
            else:
                cosine_sim = float(np.dot(q_unit, c_vec / c_norm))

            # Clamp to [-1, 1] to handle floating-point drift
            cosine_sim = max(-1.0, min(1.0, cosine_sim))

            tier = thresholds.classify(cosine_sim)
            is_relevant = thresholds.is_relevant(cosine_sim)

            scores.append(SimilarityScore(
                chunk_id=chunk_id,
                cosine_similarity=cosine_sim,
                relevance_tier=tier,
                is_relevant=is_relevant,
            ))

        scores.sort(key=lambda s: s.cosine_similarity, reverse=True)
        return scores

    def score_from_retrieved(
        self,
        retrieved_chunks: list[dict],
    ) -> tuple[float | None, float | None]:
        """
        Extract max and avg cosine similarity from pre-scored retrieved chunks.
        Chunks must have a 'score' field (already computed by the retriever adapter).

        Returns:
            (max_similarity, avg_similarity) or (None, None) if no chunks.
        """
        if not retrieved_chunks:
            return None, None

        scores = [c.get("score", 0.0) for c in retrieved_chunks if "score" in c]
        if not scores:
            return None, None

        return max(scores), sum(scores) / len(scores)

    def any_relevant(self, retrieved_chunks: list[dict]) -> bool:
        """True if at least one chunk meets the relevance threshold."""
        thresholds = self._get_thresholds()
        return any(
            thresholds.is_relevant(c.get("score", 0.0))
            for c in retrieved_chunks
        )

    def relevance_ratio(self, retrieved_chunks: list[dict]) -> float:
        """Fraction of retrieved chunks that are relevant."""
        if not retrieved_chunks:
            return 0.0
        thresholds = self._get_thresholds()
        relevant = sum(
            1 for c in retrieved_chunks if thresholds.is_relevant(c.get("score", 0.0))
        )
        return relevant / len(retrieved_chunks)

    @property
    def thresholds(self) -> ThresholdSet:
        return self._get_thresholds()
