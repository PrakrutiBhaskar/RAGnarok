"""
Pipeline configuration model with full validation.
Validated against JSON Schema before any diagnostic work begins.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Supported provider enums ────────────────────────────────────────────────

VectorDBProvider = Literal["chroma", "pinecone", "qdrant"]
EmbeddingProvider = Literal["openai", "cohere", "huggingface"]
LLMProvider = Literal["openai", "anthropic", "ollama", "groq"]
ChunkingStrategy = Literal["fixed", "sentence", "recursive", "semantic"]


# ── Sub-models ──────────────────────────────────────────────────────────────

class VectorDBConfig(BaseModel):
    """Vector database connection configuration."""

    provider: VectorDBProvider
    collection_name: str = Field(..., min_length=1, max_length=256)

    # Chroma-specific
    host: str | None = Field(None, description="Chroma host (default: localhost)")
    port: int | None = Field(None, ge=1, le=65535, description="Chroma port (default: 8000)")
    persist_directory: str | None = Field(None, description="Chroma local persistence path")

    # Pinecone-specific
    index_name: str | None = Field(None, description="Pinecone index name")
    namespace: str | None = Field(None, description="Pinecone namespace (optional)")
    environment: str | None = Field(None, description="Pinecone environment (legacy)")

    # Qdrant-specific
    url: str | None = Field(None, description="Qdrant URL")

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "VectorDBConfig":
        if self.provider == "pinecone" and not self.index_name:
            raise ValueError("index_name is required for Pinecone provider")
        if self.provider == "qdrant" and not self.url:
            raise ValueError("url is required for Qdrant provider")
        return self


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""

    provider: EmbeddingProvider
    model_id: str = Field(..., min_length=1, description="Model identifier (e.g. text-embedding-3-small)")
    dimensions: int | None = Field(None, ge=64, le=8192, description="Output dimensions (if configurable)")

    # HuggingFace-specific
    device: Literal["cpu", "cuda", "mps"] | None = Field(None)


class LLMConfig(BaseModel):
    """LLM configuration for generation diagnostics (oracle injection)."""

    provider: LLMProvider
    model_id: str = Field(..., min_length=1, description="Model identifier (e.g. gpt-4o-mini)")

    # Generation params
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(1024, ge=64, le=32768)

    # Ollama-specific
    base_url: str | None = Field(None, description="Ollama base URL (default: http://localhost:11434)")

    # System prompt override (for pipelines that use custom system prompts)
    system_prompt: str | None = Field(None, max_length=8192)


class ChunkingConfig(BaseModel):
    """Chunking strategy configuration for BM25 oracle indexing."""

    strategy: ChunkingStrategy = "recursive"
    chunk_size: Annotated[int, Field(ge=64, le=8192)] = 512
    chunk_overlap: Annotated[int, Field(ge=0, le=2048)] = 64

    @model_validator(mode="after")
    def validate_overlap(self) -> "ChunkingConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self


class RetrievalConfig(BaseModel):
    """Retrieval configuration."""

    top_k: Annotated[int, Field(ge=1, le=50)] = 5
    score_threshold: float | None = Field(None, ge=0.0, le=1.0, description="Min similarity score to include chunk")
    search_type: Literal["similarity", "mmr", "hybrid"] = "similarity"


class PromptConfig(BaseModel):
    """Prompt configuration — used to re-run generation with oracle chunks."""

    template: str = Field(
        ...,
        min_length=10,
        description="Prompt template. Must contain {context} and {question} placeholders.",
    )
    context_key: str = Field("context", description="Placeholder name for retrieved context")
    question_key: str = Field("question", description="Placeholder name for user query")

    @field_validator("template")
    @classmethod
    def validate_placeholders(cls, v: str) -> str:
        if "{context}" not in v and "{question}" not in v:
            raise ValueError("Prompt template must contain at least one of: {context}, {question}")
        return v


# ── Root model ───────────────────────────────────────────────────────────────

class PipelineConfig(BaseModel):
    """
    Root pipeline configuration model.
    Accepted as YAML input; validated before any diagnostic work.
    """

    # Required
    name: str = Field(..., min_length=1, max_length=256, description="Human-readable pipeline name")
    vector_db: VectorDBConfig
    embedding: EmbeddingConfig
    llm: LLMConfig
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    prompt: PromptConfig | None = Field(None, description="Required for generation diagnostic (oracle injection)")

    # Metadata
    description: str | None = Field(None, max_length=1024)
    tags: list[str] = Field(default_factory=list)

    # Diagnostic options
    enable_llm_judge: bool = Field(
        False,
        description="If True, sends chunk content to LLM for quality evaluation. Requires explicit acknowledgment.",
    )
    llm_judge_acknowledged: bool = Field(
        False,
        description="Must be True if enable_llm_judge=True. Explicit data sharing acknowledgment.",
    )

    @model_validator(mode="after")
    def validate_llm_judge_acknowledgment(self) -> "PipelineConfig":
        if self.enable_llm_judge and not self.llm_judge_acknowledged:
            raise ValueError(
                "llm_judge_acknowledged must be True when enable_llm_judge=True. "
                "Setting this to True means you acknowledge that chunk content will be "
                "sent to an external LLM API."
            )
        return self

    @model_validator(mode="after")
    def validate_generation_diagnostic_ready(self) -> "PipelineConfig":
        """Warn (not error) if prompt is missing — generation diagnostic will be skipped."""
        # We allow missing prompt; generation diagnostic engine will handle gracefully
        return self

    def fingerprint(self) -> str:
        """Deterministic SHA-256 hash of the config for deduplication."""
        import hashlib
        import json

        config_dict = self.model_dump(exclude={"tags", "description"})
        serialized = json.dumps(config_dict, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:64]

    class Config:
        json_schema_extra: dict[str, Any] = {
            "example": {
                "name": "Customer Support RAG Pipeline",
                "vector_db": {
                    "provider": "chroma",
                    "collection_name": "support_docs",
                    "host": "localhost",
                    "port": 8000,
                },
                "embedding": {
                    "provider": "openai",
                    "model_id": "text-embedding-3-small",
                },
                "llm": {
                    "provider": "openai",
                    "model_id": "gpt-4o-mini",
                    "temperature": 0.0,
                },
                "retrieval": {"top_k": 5},
                "prompt": {
                    "template": "Answer the question using only the context below.\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:",
                },
            }
        }


# ── Query input models ────────────────────────────────────────────────────────

class FailingQuery(BaseModel):
    """A single failing query submitted for diagnosis."""

    query: str = Field(..., min_length=1, max_length=4096)
    expected_answer: str | None = Field(None, max_length=8192)
    actual_answer: str | None = Field(None, max_length=8192)

    # Pre-retrieved chunks (optional; tool will re-retrieve regardless)
    retrieved_chunks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Chunks already retrieved by the user's pipeline (for reference/comparison)",
    )


class QueryBatch(BaseModel):
    """Batch of failing queries submitted with a session."""

    queries: list[FailingQuery] = Field(..., min_length=1, max_length=100)

    @field_validator("queries")
    @classmethod
    def validate_min_for_pattern_analysis(cls, v: list[FailingQuery]) -> list[FailingQuery]:
        # Not an error — just fewer than 3 disables pattern-level recommendations
        return v

    @property
    def is_supervised(self) -> bool:
        """Supervised mode: at least one query has an expected_answer."""
        return any(q.expected_answer is not None for q in self.queries)