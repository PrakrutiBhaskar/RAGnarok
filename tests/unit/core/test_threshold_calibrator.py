"""Unit tests for ThresholdCalibrator."""

import pytest
from backend.core.threshold_calibrator import ThresholdCalibrator


@pytest.fixture
def calibrator():
    return ThresholdCalibrator()


class TestThresholdCalibrator:
    def test_known_model_returns_lookup(self, calibrator):
        ts = calibrator.get_thresholds("text-embedding-3-small")
        assert ts.model_id == "text-embedding-3-small"
        assert 0.0 < ts.p25 < ts.p50 < ts.p75 < 1.0

    def test_unknown_model_returns_fallback(self, calibrator):
        ts = calibrator.get_thresholds("some-unknown-model-v99")
        assert ts.is_calibrated is False
        assert 0.0 < ts.p50 < 1.0

    def test_classify_high(self, calibrator):
        ts = calibrator.get_thresholds("text-embedding-3-small")
        assert ts.classify(ts.p75 + 0.01) == "high"

    def test_classify_medium(self, calibrator):
        ts = calibrator.get_thresholds("text-embedding-3-small")
        assert ts.classify(ts.p50 + 0.01) == "medium"

    def test_classify_low(self, calibrator):
        ts = calibrator.get_thresholds("text-embedding-3-small")
        assert ts.classify(ts.p25 - 0.01) == "low"

    def test_is_relevant_above_p50(self, calibrator):
        ts = calibrator.get_thresholds("text-embedding-3-small")
        assert ts.is_relevant(ts.p50 + 0.01) is True
        assert ts.is_relevant(ts.p50 - 0.01) is False

    def test_calibrate_from_sample_produces_thresholds(self, calibrator):
        import random
        samples = [random.uniform(0.2, 0.9) for _ in range(100)]
        ts = calibrator.calibrate_from_sample("custom-model", samples)
        assert ts.is_calibrated is True
        assert ts.sample_size == 100
        assert ts.p25 < ts.p50 < ts.p75

    def test_calibrate_from_small_sample_uses_fallback(self, calibrator):
        ts = calibrator.calibrate_from_sample("custom-model", [0.5, 0.6])
        assert ts.is_calibrated is False

    def test_is_known_model(self, calibrator):
        assert calibrator.is_known_model("text-embedding-ada-002") is True
        assert calibrator.is_known_model("nonexistent-model") is False
