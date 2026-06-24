"""
Abstract adapter base classes.
The adapter layer is the extensibility surface — adding a new vector DB,
embedding model, or LLM requires implementing one class from this file.
The core diagnostic logic NEVER imports specific vendor SDKs directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RetrieverAdapter(ABC):
    """Abstract interface for vector database retrieval."""

    @abstractmethod
    async def retrieve(
        self,
        query_embedding: list[float],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve top_k chunks from the vector index.

        Returns:
            List of dicts with keys:
              - chunk_id: str
              - text: str
              - score: float  (cosine similarity or provider-specific score)
              - metadata: dict
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the vector DB is reachable, False otherwise."""
        ...

    @abstractmethod
    async def get_corpus_chunks(self, limit: int = 100_000) -> list[dict[str, Any]]:
        """
        Fetch raw chunks for BM25 oracle indexing.
        Returns list of dicts with: chunk_id, text, metadata.
        MUST return at most `limit` chunks (BM25 memory constraint).
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'chroma', 'pinecone')."""
        ...


class EmbeddingAdapter(ABC):
    """Abstract interface for embedding models."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string. Returns a float vector."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float vectors."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the embedding API is reachable, False otherwise."""
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Canonical model identifier used for threshold lookup."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'openai', 'cohere')."""
        ...

    @property
    def dimensions(self) -> int | None:
        """Output dimensions, if known."""
        return None


class LLMAdapter(ABC):
    """Abstract interface for LLM generation (used in oracle injection test)."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a completion. Returns the raw text response."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the LLM API is reachable, False otherwise."""
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Model identifier."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name (e.g. 'openai', 'anthropic', 'ollama')."""
        ...


class AdapterError(Exception):
    """Raised when an adapter operation fails (network, auth, rate limit, etc.)."""

    def __init__(self, provider: str, operation: str, message: str) -> None:
        self.provider = provider
        self.operation = operation
        super().__init__(f"[{provider}] {operation} failed: {message}")


class AdapterUnavailableError(AdapterError):
    """Raised when a provider is unreachable (network timeout, DNS failure, etc.)."""
    pass


class AdapterAuthError(AdapterError):
    """Raised when API key is invalid or missing."""
    pass


class AdapterRateLimitError(AdapterError):
    """Raised when the provider returns a rate limit error."""
    pass
