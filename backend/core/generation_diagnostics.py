"""
Generation Diagnostic Engine.
Uses oracle injection to isolate generation-layer failures.

CRITICAL INVARIANT: Oracle chunks come from BM25, NEVER from the vector DB being diagnosed.
This is enforced here — this file has no reference to RetrieverAdapter.

Oracle injection test:
  1. Take the BM25 oracle chunks (best possible context for this query)
  2. Inject them into the prompt as if they were retrieved chunks
  3. Run the LLM to generate an oracle answer
  4. Compare oracle answer to actual answer
  5. If oracle answer is better → generation is NOT the problem (retrieval is)
  6. If oracle answer is also poor → generation IS the problem (prompt, LLM, etc.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.adapters.base import AdapterUnavailableError, LLMAdapter
from backend.core.bm25_engine import BM25Result
from backend.models.config import PromptConfig
from backend.models.session import GenerationVerdict

logger = logging.getLogger(__name__)


@dataclass
class GenerationDiagnosisResult:
    """Output of the generation diagnostic for one query."""

    verdict: GenerationVerdict
    oracle_answer: str | None = None
    actual_answer: str | None = None
    oracle_quality_score: float | None = None  # 0.0–1.0, higher = better oracle answer
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    skipped_reason: str | None = None


class GenerationDiagnosticEngine:
    """
    Diagnoses the generation layer via oracle chunk injection.

    Requires:
    - An LLMAdapter (to generate oracle answer)
    - A PromptConfig (to reconstruct the prompt with oracle chunks)
    - BM25 oracle chunks (already retrieved by RetrievalDiagnosticEngine)
    """

    def __init__(
        self,
        llm: LLMAdapter,
        prompt_config: PromptConfig | None,
    ) -> None:
        self._llm = llm
        self._prompt_config = prompt_config

    async def diagnose(
        self,
        query: str,
        oracle_chunks: list[BM25Result],
        actual_answer: str | None = None,
        expected_answer: str | None = None,
        redact_pii: bool = False,
    ) -> GenerationDiagnosisResult:
        """
        Run generation diagnostics for a single query using BM25 oracle chunks.
        """
        # Skip if no prompt config (can't reconstruct prompt)
        if not self._prompt_config:
            return GenerationDiagnosisResult(
                verdict="SKIPPED",
                skipped_reason="No prompt_config provided in pipeline config. "
                               "Add a prompt config to enable generation diagnostics.",
                confidence=0.0,
                evidence={"skipped": True},
            )

        # Skip if no oracle chunks (BM25 found nothing — likely data quality issue)
        if not oracle_chunks:
            return GenerationDiagnosisResult(
                verdict="SKIPPED",
                skipped_reason="No oracle chunks available from BM25 (corpus may be empty or not indexed).",
                confidence=0.0,
                evidence={"oracle_chunk_count": 0},
            )

        # Build oracle prompt
        oracle_context = self._format_oracle_context(oracle_chunks, redact_pii=redact_pii)
        oracle_prompt = self._build_prompt(query=query, context=oracle_context)

        # Run LLM with oracle context
        oracle_answer: str | None = None
        try:
            oracle_answer = await self._llm.generate(
                prompt=oracle_prompt,
                system_prompt=self._prompt_config.system_prompt if hasattr(self._prompt_config, 'system_prompt') else None,
                temperature=0.0,
                max_tokens=1024,
            )
        except AdapterUnavailableError as e:
            logger.warning("GenerationDiagnosticEngine: LLM unavailable: %s", e)
            return GenerationDiagnosisResult(
                verdict="SKIPPED",
                skipped_reason=f"LLM unavailable: {e}",
                confidence=0.0,
                evidence={"llm_error": str(e)},
            )

        # Evaluate oracle answer quality
        quality_score, verdict, confidence, evidence = self._evaluate_oracle_answer(
            oracle_answer=oracle_answer,
            actual_answer=actual_answer,
            expected_answer=expected_answer,
            oracle_chunk_count=len(oracle_chunks),
        )

        return GenerationDiagnosisResult(
            verdict=verdict,
            oracle_answer=oracle_answer,
            actual_answer=actual_answer,
            oracle_quality_score=quality_score,
            confidence=confidence,
            evidence=evidence,
        )

    def _format_oracle_context(
        self,
        chunks: list[BM25Result],
        redact_pii: bool = False,
    ) -> str:
        """Format BM25 oracle chunks into a context string for prompt injection."""
        if redact_pii:
            from backend.security.pii_redactor import redact
            texts = [redact(chunk.text) for chunk in chunks]
        else:
            texts = [chunk.text for chunk in chunks]

        return "\n\n---\n\n".join(
            f"[Source {i+1}]\n{text}"
            for i, text in enumerate(texts)
        )

    def _build_prompt(self, query: str, context: str) -> str:
        """Substitute context and query into the prompt template."""
        cfg = self._prompt_config
        assert cfg is not None

        context_key = getattr(cfg, 'context_key', 'context')
        question_key = getattr(cfg, 'question_key', 'question')

        prompt = cfg.template
        prompt = prompt.replace(f"{{{context_key}}}", context)
        prompt = prompt.replace(f"{{{question_key}}}", query)
        return prompt

    def _evaluate_oracle_answer(
        self,
        oracle_answer: str,
        actual_answer: str | None,
        expected_answer: str | None,
        oracle_chunk_count: int,
    ) -> tuple[float, GenerationVerdict, float, dict[str, Any]]:
        """
        Evaluate oracle answer quality.

        Heuristics (no LLM judge by default):
        - If expected_answer provided: lexical overlap between oracle_answer and expected_answer
        - If no expected_answer: heuristic quality signals (length, non-refusal language)
        """
        evidence: dict[str, Any] = {
            "oracle_chunk_count": oracle_chunk_count,
            "oracle_answer_length": len(oracle_answer),
            "has_expected_answer": expected_answer is not None,
            "has_actual_answer": actual_answer is not None,
        }

        # Refusal / low-quality signals
        refusal_phrases = [
            "i don't know", "i cannot", "i don't have", "no information",
            "cannot answer", "not enough information", "i'm not sure",
        ]
        oracle_lower = oracle_answer.lower()
        is_refusal = any(phrase in oracle_lower for phrase in refusal_phrases)
        evidence["oracle_is_refusal"] = is_refusal

        if is_refusal or len(oracle_answer.strip()) < 20:
            # Oracle also fails → generation problem
            quality_score = 0.2
            verdict: GenerationVerdict = "GENERATION_FAIL"
            confidence = 0.70
            evidence["diagnosis_reason"] = "oracle_answer_is_refusal_or_too_short"
            return quality_score, verdict, confidence, evidence

        # Supervised mode: compare oracle answer to expected answer
        if expected_answer:
            overlap = _lexical_overlap(oracle_answer, expected_answer)
            evidence["lexical_overlap_with_expected"] = round(overlap, 4)

            if overlap >= 0.5:
                # Oracle answer matches expected → retrieval was the problem, not generation
                quality_score = overlap
                verdict = "GENERATION_OK"
                confidence = 0.75 + (overlap - 0.5) * 0.4
                evidence["diagnosis_reason"] = "oracle_answer_matches_expected"
            elif overlap >= 0.25:
                quality_score = overlap
                verdict = "GENERATION_PARTIAL"
                confidence = 0.60
                evidence["diagnosis_reason"] = "oracle_answer_partially_matches_expected"
            else:
                quality_score = overlap
                verdict = "GENERATION_FAIL"
                confidence = 0.65
                evidence["diagnosis_reason"] = "oracle_answer_does_not_match_expected"

            return quality_score, verdict, confidence, evidence

        # Unsupervised mode: heuristic quality signals only
        quality_score = _heuristic_quality(oracle_answer)
        evidence["heuristic_quality_score"] = round(quality_score, 4)

        if quality_score >= 0.6:
            verdict = "GENERATION_OK"
            confidence = 0.50  # Lower confidence in unsupervised mode
            evidence["diagnosis_reason"] = "oracle_answer_appears_substantive_unsupervised"
        else:
            verdict = "GENERATION_PARTIAL"
            confidence = 0.45
            evidence["diagnosis_reason"] = "oracle_answer_quality_uncertain_unsupervised"

        return quality_score, verdict, confidence, evidence


def _lexical_overlap(a: str, b: str) -> float:
    """
    Compute token-level F1 overlap between two strings.
    A rough proxy for answer quality without an LLM judge.
    """
    def tokenize(text: str) -> set[str]:
        import re
        tokens = re.findall(r"\b\w+\b", text.lower())
        # Remove stopwords
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "shall", "can", "to", "of",
            "in", "on", "at", "for", "with", "by", "from", "and", "or",
            "but", "not", "this", "that", "it", "its", "i", "you", "we",
        }
        return {t for t in tokens if t not in stopwords and len(t) > 2}

    tokens_a = tokenize(a)
    tokens_b = tokenize(b)

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    if not intersection:
        return 0.0

    precision = len(intersection) / len(tokens_a)
    recall = len(intersection) / len(tokens_b)
    f1 = 2 * precision * recall / (precision + recall)
    return f1


def _heuristic_quality(text: str) -> float:
    """
    Heuristic quality score for an oracle answer without ground truth.
    Based on: length, specificity signals, non-vagueness.
    Returns 0.0–1.0.
    """
    score = 0.0
    words = text.split()

    # Length signal: 50-300 words is a good answer length
    n_words = len(words)
    if n_words >= 50:
        score += 0.3
    elif n_words >= 20:
        score += 0.2
    elif n_words >= 10:
        score += 0.1

    # Specificity signal: contains numbers, proper nouns, or technical terms
    import re
    if re.search(r"\b\d+\b", text):
        score += 0.2
    if re.search(r"\b[A-Z][a-z]+\b", text):
        score += 0.1

    # Non-vagueness: not full of hedge words
    hedge_words = {"maybe", "perhaps", "possibly", "might", "could", "unclear"}
    hedge_count = sum(1 for w in words if w.lower() in hedge_words)
    if hedge_count == 0:
        score += 0.2
    elif hedge_count <= 2:
        score += 0.1

    # Sentence completion signal
    if text.strip().endswith((".", "!", "?")):
        score += 0.1

    return min(score, 1.0)
