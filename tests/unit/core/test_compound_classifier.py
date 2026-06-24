"""Unit tests for CompoundClassifier."""

import pytest
from backend.core.compound_classifier import CompoundClassifier


@pytest.fixture
def classifier():
    return CompoundClassifier()


def _classify(clf, rv, gv, rc=0.8, gc=0.8):
    return clf.classify(rv, gv, rc, gc, {}, {})


class TestCompoundClassifier:
    def test_retrieval_ok_generation_ok(self, classifier):
        r = _classify(classifier, "RETRIEVAL_OK", "GENERATION_OK")
        assert r.final_diagnosis == "no_failure_detected"
        assert r.confidence_score > 0.5

    def test_retrieval_fail_generation_ok_is_retrieval_failure(self, classifier):
        r = _classify(classifier, "RETRIEVAL_FAIL", "GENERATION_OK")
        assert r.final_diagnosis == "retrieval_failure"

    def test_retrieval_ok_generation_fail_is_generation_failure(self, classifier):
        r = _classify(classifier, "RETRIEVAL_OK", "GENERATION_FAIL")
        assert r.final_diagnosis == "generation_failure"

    def test_both_fail_is_compound(self, classifier):
        r = _classify(classifier, "RETRIEVAL_FAIL", "GENERATION_FAIL")
        assert r.final_diagnosis == "compound_failure"

    def test_data_missing_always_data_quality(self, classifier):
        for gv in ("GENERATION_OK", "GENERATION_FAIL", "SKIPPED", "UNKNOWN"):
            r = _classify(classifier, "DATA_MISSING", gv)
            assert r.final_diagnosis == "data_quality_failure", f"Failed for gv={gv}"

    def test_generation_skipped_falls_back_to_retrieval(self, classifier):
        r = _classify(classifier, "RETRIEVAL_FAIL", "SKIPPED")
        assert r.final_diagnosis == "retrieval_failure"

    def test_unknown_retrieval_is_insufficient_evidence(self, classifier):
        r = _classify(classifier, "UNKNOWN", "UNKNOWN")
        assert r.final_diagnosis == "insufficient_evidence"
        assert r.confidence_score < 0.5

    def test_confidence_is_clamped(self, classifier):
        r = _classify(classifier, "RETRIEVAL_OK", "GENERATION_OK", rc=1.5, gc=2.0)
        assert 0.0 <= r.confidence_score <= 1.0

    def test_evidence_contains_both_verdicts(self, classifier):
        r = _classify(classifier, "RETRIEVAL_OK", "GENERATION_FAIL")
        assert "retrieval_verdict" in r.evidence
        assert "generation_verdict" in r.evidence
        assert r.evidence["retrieval_verdict"] == "RETRIEVAL_OK"
