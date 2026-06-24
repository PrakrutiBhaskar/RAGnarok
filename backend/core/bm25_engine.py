"""
BM25 oracle engine.
Provides retrieval-method-independent oracle chunks for the generation diagnostic.
CRITICAL: Oracle chunks MUST come from BM25, never from the vector DB being diagnosed.
This ensures the oracle injection test is not circular.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Maximum corpus size for BM25 indexing (memory constraint)
MAX_CORPUS_CHUNKS = 100_000


@dataclass
class BM25Result:
    """A single BM25 oracle retrieval result."""

    chunk_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [t for t in text.split() if len(t) > 1]


class BM25Engine:
    """
    BM25 index over a document corpus.
    Built once per session (on first oracle retrieval call) and reused for all queries.
    """

    def __init__(self, max_chunks: int = MAX_CORPUS_CHUNKS) -> None:
        self._max_chunks = max_chunks
        self._corpus_chunks: list[dict[str, Any]] = []
        self._bm25: Any = None
        self._tokenized_corpus: list[list[str]] = []
        self._is_indexed = False

    def index(self, chunks: list[dict[str, Any]]) -> None:
        """
        Build BM25 index from corpus chunks.
        Each chunk must have 'chunk_id', 'text', and optionally 'metadata'.

        Args:
            chunks: List of chunk dicts from RetrieverAdapter.get_corpus_chunks()
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as e:
            raise ImportError(
                "rank-bm25 is not installed. Run: pip install rank-bm25"
            ) from e

        if len(chunks) > self._max_chunks:
            logger.warning(
                "BM25Engine: corpus has %d chunks, exceeding limit of %d. "
                "Truncating to first %d chunks.",
                len(chunks), self._max_chunks, self._max_chunks,
            )
            chunks = chunks[:self._max_chunks]

        self._corpus_chunks = chunks
        self._tokenized_corpus = [_tokenize(chunk["text"]) for chunk in chunks]
        self._bm25 = BM25Okapi(self._tokenized_corpus)
        self._is_indexed = True

        logger.info("BM25Engine: indexed %d chunks", len(chunks))

    def retrieve(self, query: str, top_k: int = 5) -> list[BM25Result]:
        """
        Retrieve top_k chunks by BM25 score for a given query.

        Returns results sorted by score descending.
        Returns empty list if not indexed (graceful degradation).
        """
        if not self._is_indexed or self._bm25 is None:
            logger.warning("BM25Engine: not indexed — returning empty oracle results")
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            logger.debug("BM25Engine: empty query tokens for query '%s'", query[:50])
            return []

        scores = self._bm25.get_scores(query_tokens)

        # Get top_k indices by score
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0.0:
                continue  # Skip irrelevant results
            chunk = self._corpus_chunks[idx]
            results.append(BM25Result(
                chunk_id=chunk.get("chunk_id", str(idx)),
                text=chunk["text"],
                score=score,
                metadata=chunk.get("metadata", {}),
            ))

        return results

    def is_answer_in_corpus(self, expected_answer: str, threshold: float = 0.5) -> bool:
        """
        Heuristic check: does the corpus contain text that could answer this query?
        Used to distinguish 'data quality failure' from 'retrieval failure'.
        """
        if not self._is_indexed or not expected_answer:
            return False

        results = self.retrieve(expected_answer, top_k=3)
        if not results:
            return False

        # Normalize score against max possible BM25 score for this query
        max_score = results[0].score
        return max_score >= threshold

    @property
    def corpus_size(self) -> int:
        return len(self._corpus_chunks)

    @property
    def is_indexed(self) -> bool:
        return self._is_indexed
