"""OpenAI embedding adapter."""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.adapters.base import (
    AdapterAuthError,
    AdapterRateLimitError,
    AdapterUnavailableError,
    EmbeddingAdapter,
)
from backend.models.config import EmbeddingConfig

logger = logging.getLogger(__name__)


class OpenAIEmbeddingAdapter(EmbeddingAdapter):
    """Embedding adapter for OpenAI text-embedding models."""

    # Supported models and their dimensions
    KNOWN_DIMENSIONS: dict[str, int] = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError(
                "openai is not installed. Run: pip install openai"
            ) from e

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise AdapterAuthError(
                "openai", "init", "OPENAI_API_KEY environment variable is not set"
            )

        self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. OpenAI supports up to 2048 inputs per request."""
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": self._config.model_id,
            "input": texts,
            "encoding_format": "float",
        }
        if self._config.dimensions:
            kwargs["dimensions"] = self._config.dimensions

        try:
            response = await client.embeddings.create(**kwargs)
            # Sort by index to guarantee order
            embeddings = sorted(response.data, key=lambda e: e.index)
            return [e.embedding for e in embeddings]

        except Exception as e:
            err_str = str(e).lower()
            if "authentication" in err_str or "invalid api key" in err_str or "401" in err_str:
                raise AdapterAuthError("openai", "embed", str(e)) from e
            if "rate limit" in err_str or "429" in err_str:
                raise AdapterRateLimitError("openai", "embed", str(e)) from e
            if "connection" in err_str or "timeout" in err_str:
                raise AdapterUnavailableError("openai", "embed", str(e)) from e
            raise

    async def health_check(self) -> bool:
        try:
            await self.embed_query("health check")
            return True
        except Exception as e:
            logger.warning("OpenAIEmbeddingAdapter health check failed: %s", e)
            return False

    @property
    def model_id(self) -> str:
        return self._config.model_id

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def dimensions(self) -> int | None:
        if self._config.dimensions:
            return self._config.dimensions
        return self.KNOWN_DIMENSIONS.get(self._config.model_id)
