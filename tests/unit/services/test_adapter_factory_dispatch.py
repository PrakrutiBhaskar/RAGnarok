"""Tests for SessionService's adapter factory dispatch (_build_retriever/_build_embedder/_build_llm).

These were untested (0% on the corresponding lines) despite being the exact
place where the README's provider-support claims are enforced or violated —
this is where "Unsupported provider" errors actually get raised for
Pinecone/Qdrant/Cohere/Anthropic/Ollama, which are schema-valid but
unimplemented.
"""

from __future__ import annotations

import pytest

from backend.adapters.embeddings.huggingface_embed import HuggingFaceEmbeddingAdapter
from backend.adapters.embeddings.openai_embed import OpenAIEmbeddingAdapter
from backend.adapters.llms.groq_llm import GroqLLMAdapter
from backend.adapters.llms.openai_llm import OpenAILLMAdapter
from backend.adapters.retrievers.chroma_adapter import ChromaAdapter
from backend.models.config import (
    ChunkingConfig,
    EmbeddingConfig,
    LLMConfig,
    PipelineConfig,
    RetrievalConfig,
    VectorDBConfig,
)
from backend.services.session_service import SessionService


def make_config(vector_db_provider="chroma", embedding_provider="openai", llm_provider="openai"):
    vector_db_kwargs = {"provider": vector_db_provider, "collection_name": "docs"}
    if vector_db_provider == "pinecone":
        vector_db_kwargs["index_name"] = "docs-index"
    elif vector_db_provider == "qdrant":
        vector_db_kwargs["url"] = "http://localhost:6333"

    return PipelineConfig(
        name="Test",
        vector_db=VectorDBConfig(**vector_db_kwargs),
        embedding=EmbeddingConfig(provider=embedding_provider, model_id="m"),
        llm=LLMConfig(provider=llm_provider, model_id="m"),
        chunking=ChunkingConfig(),
        retrieval=RetrievalConfig(),
    )


class TestBuildRetriever:
    def test_chroma_returns_chroma_adapter(self, db_session):
        service = SessionService(db_session)
        result = service._build_retriever(make_config(vector_db_provider="chroma"))
        assert isinstance(result, ChromaAdapter)

    def test_unsupported_provider_raises_value_error(self, db_session):
        service = SessionService(db_session)
        # pinecone/qdrant are valid per the config schema (Literal type) but
        # have no adapter implementation — confirms the ValueError path the
        # README now correctly documents as "raises a clear error".
        with pytest.raises(ValueError, match="Unsupported vector DB provider: pinecone"):
            service._build_retriever(make_config(vector_db_provider="pinecone"))


class TestBuildEmbedder:
    def test_openai_returns_openai_adapter(self, db_session):
        service = SessionService(db_session)
        result = service._build_embedder(make_config(embedding_provider="openai"))
        assert isinstance(result, OpenAIEmbeddingAdapter)

    def test_huggingface_returns_huggingface_adapter(self, db_session):
        service = SessionService(db_session)
        result = service._build_embedder(make_config(embedding_provider="huggingface"))
        assert isinstance(result, HuggingFaceEmbeddingAdapter)


class TestBuildLLM:
    def test_openai_returns_openai_adapter(self, db_session):
        service = SessionService(db_session)
        result = service._build_llm(make_config(llm_provider="openai"))
        assert isinstance(result, OpenAILLMAdapter)

    def test_groq_returns_groq_adapter(self, db_session):
        service = SessionService(db_session)
        result = service._build_llm(make_config(llm_provider="groq"))
        assert isinstance(result, GroqLLMAdapter)
