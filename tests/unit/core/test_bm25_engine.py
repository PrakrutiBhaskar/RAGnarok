"""Unit tests for BM25Engine."""

import pytest
from backend.core.bm25_engine import BM25Engine


CORPUS = [
    {"chunk_id": "c1", "text": "The Eiffel Tower is located in Paris, France."},
    {"chunk_id": "c2", "text": "Python is a high-level programming language."},
    {"chunk_id": "c3", "text": "Machine learning models require large datasets."},
    {"chunk_id": "c4", "text": "The Louvre museum is also in Paris, near the Seine river."},
    {"chunk_id": "c5", "text": "Deep learning is a subset of machine learning."},
]


@pytest.fixture
def indexed_engine():
    engine = BM25Engine()
    engine.index(CORPUS)
    return engine


class TestBM25Engine:
    def test_index_builds_correctly(self, indexed_engine):
        assert indexed_engine.is_indexed
        assert indexed_engine.corpus_size == 5

    def test_retrieve_returns_relevant_results(self, indexed_engine):
        results = indexed_engine.retrieve("Paris tourist attractions", top_k=2)
        assert len(results) > 0
        chunk_ids = [r.chunk_id for r in results]
        # Both Paris chunks should score well
        assert any(cid in ("c1", "c4") for cid in chunk_ids)

    def test_retrieve_empty_query_returns_empty(self, indexed_engine):
        results = indexed_engine.retrieve("", top_k=5)
        assert results == []

    def test_retrieve_respects_top_k(self, indexed_engine):
        results = indexed_engine.retrieve("machine learning deep neural", top_k=2)
        assert len(results) <= 2

    def test_retrieve_scores_are_positive(self, indexed_engine):
        results = indexed_engine.retrieve("programming language Python", top_k=3)
        for r in results:
            assert r.score > 0.0

    def test_retrieve_sorted_descending(self, indexed_engine):
        results = indexed_engine.retrieve("machine learning", top_k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_answer_in_corpus_true(self, indexed_engine):
        assert indexed_engine.is_answer_in_corpus("Paris Eiffel Tower France")

    def test_answer_in_corpus_false_for_unrelated(self, indexed_engine):
        # "quantum physics" has no presence in corpus
        result = indexed_engine.is_answer_in_corpus("quantum physics neutron star")
        assert result is False

    def test_not_indexed_returns_empty(self):
        engine = BM25Engine()
        results = engine.retrieve("anything", top_k=5)
        assert results == []

    def test_corpus_truncation(self):
        engine = BM25Engine(max_chunks=3)
        big_corpus = [{"chunk_id": f"c{i}", "text": f"Document {i} content here."} for i in range(10)]
        engine.index(big_corpus)
        assert engine.corpus_size == 3
