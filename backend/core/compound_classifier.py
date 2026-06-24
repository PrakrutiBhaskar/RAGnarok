"""
Compound classifier — combines retrieval and generation verdicts into a final diagnosis.

Classification matrix:
  RETRIEVAL_OK  + GENERATION_OK    → no_failure_detected
  RETRIEVAL_OK  + GENERATION_FAIL  → generation_failure
  RETRIEVAL_FAIL + GENERATION_OK   → retrieval_failure        (oracle succeeded)
  RETRIEVAL_FAIL + GENERATION_FAIL → compound_failure
  RETRIEVAL_FAIL + SKIPPED         → retrieval_failure
  DATA_MISSING  + *                → data_quality_failure
  RETRIEVAL_PARTIAL + *            → retrieval_failure (partial) or compound_failure
  * + UNKNOWN / insufficient evidence → insufficient_evidence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.models.session import FinalDiagnosis, GenerationVerdict, RetrievalVerdict


@dataclass
class ClassificationResult:
    final_diagnosis: FinalDiagnosis
    confidence_score: float
    evidence: dict[str, Any]


# Classification matrix: (retrieval_verdict, generation_verdict) → diagnosis
_MATRIX: dict[tuple[str, str], FinalDiagnosis] = {
    # Clear successes
    ("RETRIEVAL_OK", "GENERATION_OK"):      "no_failure_detected",
    ("RETRIEVAL_OK", "GENERATION_PARTIAL"): "generation_failure",
    ("RETRIEVAL_OK", "GENERATION_FAIL"):    "generation_failure",

    # Data quality failure (supersedes other verdicts)
    ("DATA_MISSING", "GENERATION_OK"):      "data_quality_failure",
    ("DATA_MISSING", "GENERATION_FAIL"):    "data_quality_failure",
    ("DATA_MISSING", "GENERATION_PARTIAL"): "data_quality_failure",
    ("DATA_MISSING", "SKIPPED"):            "data_quality_failure",
    ("DATA_MISSING", "UNKNOWN"):            "data_quality_failure",

    # Retrieval failures (oracle injection confirms generation works with good context)
    ("RETRIEVAL_FAIL", "GENERATION_OK"):      "retrieval_failure",
    ("RETRIEVAL_FAIL", "GENERATION_PARTIAL"): "retrieval_failure",
    ("RETRIEVAL_PARTIAL", "GENERATION_OK"):   "retrieval_failure",
    ("RETRIEVAL_PARTIAL", "GENERATION_PARTIAL"): "retrieval_failure",

    # Compound failures (both layers broken)
    ("RETRIEVAL_FAIL", "GENERATION_FAIL"):    "compound_failure",
    ("RETRIEVAL_PARTIAL", "GENERATION_FAIL"): "compound_failure",

    # Generation skipped — fall back to retrieval verdict only
    ("RETRIEVAL_FAIL", "SKIPPED"):    "retrieval_failure",
    ("RETRIEVAL_OK", "SKIPPED"):      "no_failure_detected",
    ("RETRIEVAL_PARTIAL", "SKIPPED"): "retrieval_failure",

    # Unknown retrieval verdict
    ("UNKNOWN", "GENERATION_OK"):   "insufficient_evidence",
    ("UNKNOWN", "GENERATION_FAIL"): "insufficient_evidence",
    ("UNKNOWN", "SKIPPED"):         "insufficient_evidence",
    ("UNKNOWN", "UNKNOWN"):         "insufficient_evidence",
    ("RETRIEVAL_FAIL", "UNKNOWN"):  "retrieval_failure",   # Best guess
    ("RETRIEVAL_OK", "UNKNOWN"):    "insufficient_evidence",
}

# Confidence modifiers based on verdict combination
_CONFIDENCE_MODIFIERS: dict[tuple[str, str], float] = {
    ("DATA_MISSING", "SKIPPED"):            0.85,   # High — corpus evidence is clear
    ("RETRIEVAL_FAIL", "GENERATION_OK"):    0.90,   # High — oracle injection confirmed
    ("RETRIEVAL_OK", "GENERATION_FAIL"):    0.85,
    ("RETRIEVAL_FAIL", "GENERATION_FAIL"):  0.70,   # Lower — compound is ambiguous
    ("UNKNOWN", "UNKNOWN"):                 0.10,
}

# LOW_CONFIDENCE threshold
LOW_CONFIDENCE_THRESHOLD = 0.5


class CompoundClassifier:
    """
    Combines retrieval and generation verdicts into a final FinalDiagnosis.
    Computes a composite confidence score from both diagnostic components.
    """

    def classify(
        self,
        retrieval_verdict: RetrievalVerdict,
        generation_verdict: GenerationVerdict,
        retrieval_confidence: float,
        generation_confidence: float,
        retrieval_evidence: dict[str, Any],
        generation_evidence: dict[str, Any],
    ) -> ClassificationResult:
        key = (retrieval_verdict, generation_verdict)
        final_diagnosis = _MATRIX.get(key, "insufficient_evidence")

        # Composite confidence
        if generation_verdict == "SKIPPED":
            # Only retrieval confidence
            composite_confidence = retrieval_confidence * 0.9
        else:
            # Weighted average: retrieval and generation are equally weighted
            composite_confidence = (retrieval_confidence + generation_confidence) / 2.0

        # Apply matrix-level modifier if available
        if key in _CONFIDENCE_MODIFIERS:
            composite_confidence = min(
                composite_confidence,
                _CONFIDENCE_MODIFIERS[key],
            )

        # Clamp
        composite_confidence = max(0.0, min(1.0, composite_confidence))

        # Low confidence flag
        low_confidence = composite_confidence < LOW_CONFIDENCE_THRESHOLD

        evidence = {
            "retrieval_verdict": retrieval_verdict,
            "generation_verdict": generation_verdict,
            "retrieval_confidence": round(retrieval_confidence, 4),
            "generation_confidence": round(generation_confidence, 4),
            "composite_confidence": round(composite_confidence, 4),
            "low_confidence": low_confidence,
            "matrix_key": f"{retrieval_verdict}+{generation_verdict}",
            "retrieval_evidence": retrieval_evidence,
            "generation_evidence": generation_evidence,
        }

        return ClassificationResult(
            final_diagnosis=final_diagnosis,
            confidence_score=round(composite_confidence, 4),
            evidence=evidence,
        )
