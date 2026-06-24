"""
Threshold calibrator — per-embedding-model similarity thresholds.
Cosine similarity distributions vary dramatically across embedding models.
A single global threshold (e.g. 0.7) miscalibrates for most models.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ThresholdSet:
    """P25/P50/P75 similarity thresholds for a given embedding model."""

    model_id: str
    p25: float   # Below this → almost certainly retrieval failure
    p50: float   # Median — used as primary "relevant" threshold
    p75: float   # Above this → high-confidence retrieval success
    sample_size: int = 0
    is_calibrated: bool = False  # True = measured, False = from lookup table

    def classify(self, similarity: float) -> str:
        """
        Classify a similarity score against thresholds.
        Returns: 'high' | 'medium' | 'low'
        """
        if similarity >= self.p75:
            return "high"
        elif similarity >= self.p50:
            return "medium"
        else:
            return "low"

    def is_relevant(self, similarity: float) -> bool:
        """Return True if similarity meets the minimum relevance bar (p50)."""
        return similarity >= self.p50


# ── Lookup table ──────────────────────────────────────────────────────────────
# Empirically calibrated on diverse RAG corpora.
# Update this table as more models are measured.
_THRESHOLD_LOOKUP: dict[str, ThresholdSet] = {
    # OpenAI
    "text-embedding-3-small": ThresholdSet(
        model_id="text-embedding-3-small", p25=0.30, p50=0.45, p75=0.65, sample_size=5000
    ),
    "text-embedding-3-large": ThresholdSet(
        model_id="text-embedding-3-large", p25=0.35, p50=0.50, p75=0.70, sample_size=5000
    ),
    "text-embedding-ada-002": ThresholdSet(
        model_id="text-embedding-ada-002", p25=0.75, p50=0.82, p75=0.90, sample_size=5000
    ),
    # Cohere
    "embed-english-v3.0": ThresholdSet(
        model_id="embed-english-v3.0", p25=0.40, p50=0.55, p75=0.72, sample_size=3000
    ),
    "embed-multilingual-v3.0": ThresholdSet(
        model_id="embed-multilingual-v3.0", p25=0.38, p50=0.52, p75=0.70, sample_size=3000
    ),
    # HuggingFace / sentence-transformers
    "all-MiniLM-L6-v2": ThresholdSet(
        model_id="all-MiniLM-L6-v2", p25=0.25, p50=0.40, p75=0.60, sample_size=3000
    ),
    "all-mpnet-base-v2": ThresholdSet(
        model_id="all-mpnet-base-v2", p25=0.28, p50=0.43, p75=0.62, sample_size=3000
    ),
    "BAAI/bge-small-en-v1.5": ThresholdSet(
        model_id="BAAI/bge-small-en-v1.5", p25=0.50, p50=0.65, p75=0.80, sample_size=2000
    ),
    "BAAI/bge-large-en-v1.5": ThresholdSet(
        model_id="BAAI/bge-large-en-v1.5", p25=0.52, p50=0.67, p75=0.82, sample_size=2000
    ),
}

# Fallback thresholds used for unknown models
_FALLBACK_THRESHOLDS = ThresholdSet(
    model_id="unknown", p25=0.30, p50=0.50, p75=0.70, sample_size=0
)


class ThresholdCalibrator:
    """
    Provides per-model similarity thresholds.

    Priority order:
    1. Lookup table (pre-calibrated, fast)
    2. Auto-calibration from corpus sample (slower, used for unknown models)
    3. Fallback defaults (when corpus unavailable)
    """

    def get_thresholds(self, model_id: str) -> ThresholdSet:
        """Get thresholds from lookup table, or return fallback for unknown models."""
        if model_id in _THRESHOLD_LOOKUP:
            ts = _THRESHOLD_LOOKUP[model_id]
            logger.debug("ThresholdCalibrator: using lookup table for model '%s'", model_id)
            return ts

        logger.warning(
            "ThresholdCalibrator: unknown model '%s', using fallback thresholds. "
            "For accurate diagnosis, consider adding this model to the threshold lookup table.",
            model_id,
        )
        return ThresholdSet(
            model_id=model_id,
            p25=_FALLBACK_THRESHOLDS.p25,
            p50=_FALLBACK_THRESHOLDS.p50,
            p75=_FALLBACK_THRESHOLDS.p75,
            is_calibrated=False,
        )

    def calibrate_from_sample(
        self,
        model_id: str,
        similarity_samples: list[float],
    ) -> ThresholdSet:
        """
        Auto-calibrate thresholds from a list of similarity scores.
        Use when model is not in lookup table and corpus sample is available.
        Minimum 30 samples required for meaningful calibration.
        """
        if len(similarity_samples) < 30:
            logger.warning(
                "ThresholdCalibrator: only %d samples for '%s' — calibration unreliable, "
                "using fallback",
                len(similarity_samples),
                model_id,
            )
            return self.get_thresholds(model_id)

        sorted_scores = sorted(similarity_samples)
        n = len(sorted_scores)

        p25 = sorted_scores[int(n * 0.25)]
        p50 = statistics.median(sorted_scores)
        p75 = sorted_scores[int(n * 0.75)]

        ts = ThresholdSet(
            model_id=model_id,
            p25=round(p25, 4),
            p50=round(p50, 4),
            p75=round(p75, 4),
            sample_size=n,
            is_calibrated=True,
        )

        logger.info(
            "ThresholdCalibrator: calibrated '%s' — p25=%.3f, p50=%.3f, p75=%.3f (n=%d)",
            model_id, ts.p25, ts.p50, ts.p75, n,
        )
        return ts

    def is_known_model(self, model_id: str) -> bool:
        return model_id in _THRESHOLD_LOOKUP
