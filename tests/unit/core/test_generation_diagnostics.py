"""Unit tests for GenerationDiagnosticEngine."""

import pytest
from unittest.mock import AsyncMock
from backend.core.generation_diagnostics import GenerationDiagnosticEngine, _lexical_overlap, _heuristic_quality
from backend.core.bm25_engine import BM25Result
from backend.models.config import PromptConfig


PROMPT = PromptConfig(template="Context: {context}\n\nQuestion: {question}\n\nAnswer:")

ORACLE_CHUNKS = [
    BM25Result(chunk_id="c1", text="To reset your password, go to Settings > Security > Reset Password.", score=5.0),
    BM25Result(chunk_id="c2", text="A reset email valid for 24 hours will be sent to you.", score=3.0),
]


def make_engine(llm_response: str = "Go to Settings > Security > Reset Password."):
    llm = AsyncMock()
    llm.generate.return_value = llm_response
    return GenerationDiagnosticEngine(llm=llm, prompt_config=PROMPT)


class TestGenerationDiagnosticEngine:
    async def test_no_prompt_config_skips(self):
        llm = AsyncMock()
        engine = GenerationDiagnosticEngine(llm=llm, prompt_config=None)
        result = await engine.diagnose("test", oracle_chunks=ORACLE_CHUNKS)
        assert result.verdict == "SKIPPED"
        assert result.skipped_reason is not None

    async def test_no_oracle_chunks_skips(self):
        engine = make_engine()
        result = await engine.diagnose("test", oracle_chunks=[])
        assert result.verdict == "SKIPPED"

    async def test_good_oracle_answer_supervised(self):
        engine = make_engine("Go to Settings Security Reset Password and follow instructions.")
        result = await engine.diagnose(
            "reset password",
            oracle_chunks=ORACLE_CHUNKS,
            expected_answer="Settings > Security > Reset Password",
        )
        assert result.verdict == "GENERATION_OK"
        assert result.oracle_quality_score is not None
        assert result.oracle_quality_score > 0.3

    async def test_refusal_oracle_answer_is_generation_fail(self):
        engine = make_engine("I don't know the answer to this question.")
        result = await engine.diagnose(
            "reset password",
            oracle_chunks=ORACLE_CHUNKS,
            expected_answer="Settings > Security",
        )
        assert result.verdict == "GENERATION_FAIL"

    async def test_oracle_answer_populated(self):
        engine = make_engine("Settings > Security > Reset Password.")
        result = await engine.diagnose("reset password", oracle_chunks=ORACLE_CHUNKS)
        assert result.oracle_answer == "Settings > Security > Reset Password."

    async def test_llm_unavailable_skips(self):
        from backend.adapters.base import AdapterUnavailableError
        llm = AsyncMock()
        llm.generate.side_effect = AdapterUnavailableError("test", "generate", "timeout")
        engine = GenerationDiagnosticEngine(llm=llm, prompt_config=PROMPT)
        result = await engine.diagnose("test", oracle_chunks=ORACLE_CHUNKS)
        assert result.verdict == "SKIPPED"
        assert "llm_error" in result.evidence

    async def test_unsupervised_returns_generation_ok_for_good_answer(self):
        good_answer = (
            "To reset your password, navigate to the Settings section of your account. "
            "Click on Security and then Reset Password. An email will be sent within 5 minutes."
        )
        engine = make_engine(good_answer)
        result = await engine.diagnose("reset password", oracle_chunks=ORACLE_CHUNKS)
        # No expected_answer → unsupervised mode
        assert result.verdict in ("GENERATION_OK", "GENERATION_PARTIAL")

    async def test_evidence_populated(self):
        engine = make_engine("Settings > Security > Reset Password.")
        result = await engine.diagnose(
            "reset password",
            oracle_chunks=ORACLE_CHUNKS,
            expected_answer="Settings Security",
        )
        assert "oracle_chunk_count" in result.evidence
        assert result.evidence["oracle_chunk_count"] == 2


class TestLexicalOverlap:
    def test_identical_strings(self):
        assert _lexical_overlap("reset password settings", "reset password settings") == pytest.approx(1.0)

    def test_no_overlap(self):
        assert _lexical_overlap("quantum physics stars", "password security reset") == 0.0

    def test_partial_overlap(self):
        score = _lexical_overlap("reset password security", "password authentication")
        assert 0.0 < score < 1.0

    def test_empty_strings(self):
        assert _lexical_overlap("", "anything") == 0.0
        assert _lexical_overlap("anything", "") == 0.0

    def test_stopwords_ignored(self):
        # "the a is" are all stopwords — should result in 0 meaningful tokens
        score = _lexical_overlap("the a is", "reset password")
        assert score == 0.0


class TestHeuristicQuality:
    def test_long_specific_answer_scores_high(self):
        text = (
            "To reset your password, navigate to Settings then Security. "
            "Click Reset Password and enter your email address. "
            "You will receive a link valid for 24 hours. "
            "Follow the link and enter your new password twice."
        )
        assert _heuristic_quality(text) >= 0.5

    def test_very_short_answer_scores_low(self):
        assert _heuristic_quality("Yes.") < 0.5

    def test_empty_string_scores_zero(self):
        assert _heuristic_quality("") < 0.3

    def test_score_clamped_to_one(self):
        very_long = " ".join(["specific technical term 42"] * 100)
        assert _heuristic_quality(very_long) <= 1.0