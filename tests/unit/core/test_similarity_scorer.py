"""Unit tests for SimilarityScorer."""

import pytest
import numpy as np
from backend.core.similarity_scorer import SimilarityScorer


def make_vec(dim: int, val: float) -> list[float]:
    """Make a unit vector filled with val, normalized."""
    v = np.full(dim, val, dtype=np.float32)
    return (v / np.linalg.norm(v)).tolist()


@pytest.fixture
def scorer():
    return SimilarityScorer(model_id="text-embedding-3-small")


class TestSimilarityScorer:
    def test_identical_vectors_score_one(self, scorer):
        q = make_vec(1536, 1.0)
        results = scorer.score(q, [("c1", q)])
        assert abs(results[0].cosine_similarity - 1.0) < 1e-5

    def test_orthogonal_vectors_score_zero(self, scorer):
        q = [1.0] + [0.0] * 1535
        c = [0.0, 1.0] + [0.0] * 1534
        results = scorer.score(q, [("c1", c)])
        assert abs(results[0].cosine_similarity) < 1e-5

    def test_sorted_descending(self, scorer):
        q = make_vec(1536, 1.0)
        chunks = [
            ("c1", make_vec(1536, 0.1)),
            ("c2", make_vec(1536, 0.9)),
            ("c3", make_vec(1536, 0.5)),
        ]
        results = scorer.score(q, chunks)
        scores = [r.cosine_similarity for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_zero_norm_query_returns_empty(self, scorer):
        results = scorer.score([0.0] * 1536, [("c1", make_vec(1536, 1.0))])
        assert results == []

    def test_score_from_retrieved_empty(self, scorer):
        max_s, avg_s = scorer.score_from_retrieved([])
        assert max_s is None and avg_s is None

    def test_score_from_retrieved_values(self, scorer):
        chunks = [{"score": 0.8}, {"score": 0.4}]
        max_s, avg_s = scorer.score_from_retrieved(chunks)
        assert abs(max_s - 0.8) < 1e-6
        assert abs(avg_s - 0.6) < 1e-6

    def test_relevance_ratio_all_relevant(self, scorer):
        # p50 for text-embedding-3-small is 0.45
        chunks = [{"score": 0.9}, {"score": 0.8}, {"score": 0.7}]
        ratio = scorer.relevance_ratio(chunks)
        assert ratio == 1.0

    def test_relevance_ratio_none_relevant(self, scorer):
        chunks = [{"score": 0.1}, {"score": 0.2}]
        ratio = scorer.relevance_ratio(chunks)
        assert ratio == 0.0

    def test_any_relevant_true(self, scorer):
        assert scorer.any_relevant([{"score": 0.9}]) is True

    def test_any_relevant_false(self, scorer):
        assert scorer.any_relevant([{"score": 0.1}]) is False

    def test_relevance_ratio_empty(self, scorer):
        assert scorer.relevance_ratio([]) == 0.0

    def test_chunk_id_preserved(self, scorer):
        q = make_vec(1536, 1.0)
        results = scorer.score(q, [("my-chunk-id", q)])
        assert results[0].chunk_id == "my-chunk-id"

    def test_score_clamped_to_minus_one_plus_one(self, scorer):
        q = make_vec(16, 1.0)
        c = make_vec(16, -1.0)
        results = scorer.score(q, [("c1", c)])
        assert -1.0 <= results[0].cosine_similarity <= 1.0