"""Unit tests for RecommendationEngine."""

import pytest
from uuid import uuid4
from backend.core.recommendation_engine import RecommendationEngine


@pytest.fixture
def engine():
    return RecommendationEngine()


SESSION_ID = uuid4()


class TestRecommendationEngine:
    def test_retrieval_failure_generates_recs(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="retrieval_failure",
            failure_distribution={"retrieval_failure": 3},
            session_evidence={},
        )
        assert len(recs) > 0

    def test_generation_failure_generates_recs(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="generation_failure",
            failure_distribution={"generation_failure": 2},
            session_evidence={},
        )
        assert len(recs) > 0

    def test_data_quality_failure_generates_recs(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="data_quality_failure",
            failure_distribution={"data_quality_failure": 1},
            session_evidence={},
        )
        assert len(recs) > 0

    def test_compound_failure_generates_recs(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="compound_failure",
            failure_distribution={"compound_failure": 2},
            session_evidence={},
        )
        assert len(recs) > 0

    def test_no_failure_returns_empty(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="no_failure_detected",
            failure_distribution={"no_failure_detected": 5},
            session_evidence={},
        )
        assert recs == []

    def test_insufficient_evidence_returns_empty(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="insufficient_evidence",
            failure_distribution={"insufficient_evidence": 2},
            session_evidence={},
        )
        assert recs == []

    def test_none_dominant_returns_empty(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure=None,
            failure_distribution={},
            session_evidence={},
        )
        assert recs == []

    def test_ranks_are_sequential(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="retrieval_failure",
            failure_distribution={"retrieval_failure": 3},
            session_evidence={},
        )
        ranks = [r.rank for r in recs]
        assert ranks == list(range(1, len(recs) + 1))

    def test_sorted_by_priority_score(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="retrieval_failure",
            failure_distribution={"retrieval_failure": 3},
            session_evidence={},
        )
        priority_scores = [r.priority_score for r in recs]
        assert priority_scores == sorted(priority_scores, reverse=True)

    def test_session_id_set_on_all_recs(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="retrieval_failure",
            failure_distribution={"retrieval_failure": 2},
            session_evidence={},
        )
        for rec in recs:
            assert rec.session_id == SESSION_ID

    def test_effort_values_valid(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="retrieval_failure",
            failure_distribution={"retrieval_failure": 3},
            session_evidence={},
        )
        for rec in recs:
            assert rec.effort in ("low", "medium", "high")
            assert rec.impact in ("low", "medium", "high")

    def test_impact_scores_in_range(self, engine):
        recs = engine.generate(
            session_id=SESSION_ID,
            dominant_failure="generation_failure",
            failure_distribution={"generation_failure": 2},
            session_evidence={},
        )
        for rec in recs:
            assert 0.0 <= rec.impact_score <= 1.0
            assert 0.0 <= rec.effort_score <= 1.0