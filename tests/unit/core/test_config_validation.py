"""Unit tests for PipelineConfig validation."""

import pytest
from pydantic import ValidationError
from backend.models.config import PipelineConfig, QueryBatch


VALID_CONFIG = {
    "name": "Test Pipeline",
    "vector_db": {"provider": "chroma", "collection_name": "test_docs"},
    "embedding": {"provider": "openai", "model_id": "text-embedding-3-small"},
    "llm": {"provider": "openai", "model_id": "gpt-4o-mini"},
}


class TestPipelineConfig:
    def test_valid_config_accepted(self):
        cfg = PipelineConfig(**VALID_CONFIG)
        assert cfg.name == "Test Pipeline"
        assert cfg.vector_db.provider == "chroma"

    def test_missing_name_rejected(self):
        bad = {**VALID_CONFIG}
        del bad["name"]
        with pytest.raises(ValidationError):
            PipelineConfig(**bad)

    def test_unsupported_provider_rejected(self):
        bad = {**VALID_CONFIG, "vector_db": {"provider": "weaviate", "collection_name": "x"}}
        with pytest.raises(ValidationError):
            PipelineConfig(**bad)

    def test_pinecone_requires_index_name(self):
        bad = {**VALID_CONFIG, "vector_db": {"provider": "pinecone", "collection_name": "x"}}
        with pytest.raises(ValidationError, match="index_name"):
            PipelineConfig(**bad)

    def test_llm_judge_requires_acknowledgment(self):
        bad = {**VALID_CONFIG, "enable_llm_judge": True, "llm_judge_acknowledged": False}
        with pytest.raises(ValidationError, match="llm_judge_acknowledged"):
            PipelineConfig(**bad)

    def test_llm_judge_with_acknowledgment_passes(self):
        cfg = PipelineConfig(**{**VALID_CONFIG, "enable_llm_judge": True, "llm_judge_acknowledged": True})
        assert cfg.enable_llm_judge is True

    def test_chunk_overlap_must_be_less_than_chunk_size(self):
        bad = {**VALID_CONFIG, "chunking": {"strategy": "fixed", "chunk_size": 256, "chunk_overlap": 256}}
        with pytest.raises(ValidationError):
            PipelineConfig(**bad)

    def test_top_k_bounds(self):
        bad = {**VALID_CONFIG, "retrieval": {"top_k": 0}}
        with pytest.raises(ValidationError):
            PipelineConfig(**bad)
        bad2 = {**VALID_CONFIG, "retrieval": {"top_k": 51}}
        with pytest.raises(ValidationError):
            PipelineConfig(**bad2)

    def test_fingerprint_is_deterministic(self):
        cfg1 = PipelineConfig(**VALID_CONFIG)
        cfg2 = PipelineConfig(**VALID_CONFIG)
        assert cfg1.fingerprint() == cfg2.fingerprint()

    def test_fingerprint_changes_with_config(self):
        cfg1 = PipelineConfig(**VALID_CONFIG)
        cfg2 = PipelineConfig(**{**VALID_CONFIG, "retrieval": {"top_k": 10}})
        assert cfg1.fingerprint() != cfg2.fingerprint()

    def test_prompt_placeholder_validation(self):
        bad_prompt = {"template": "No placeholders here at all."}
        with pytest.raises(ValidationError):
            PipelineConfig(**{**VALID_CONFIG, "prompt": bad_prompt})

    def test_valid_prompt_accepted(self):
        cfg = PipelineConfig(**{**VALID_CONFIG, "prompt": {
            "template": "Context: {context}\nQuestion: {question}\nAnswer:"
        }})
        assert cfg.prompt is not None


class TestQueryBatch:
    def test_valid_batch(self):
        batch = QueryBatch(queries=[{"query": "What is X?"}])
        assert len(batch.queries) == 1

    def test_empty_batch_rejected(self):
        with pytest.raises(ValidationError):
            QueryBatch(queries=[])

    def test_supervised_mode_detected(self):
        batch = QueryBatch(queries=[{"query": "Q?", "expected_answer": "A"}])
        assert batch.is_supervised is True

    def test_unsupervised_mode_detected(self):
        batch = QueryBatch(queries=[{"query": "Q?"}])
        assert batch.is_supervised is False
