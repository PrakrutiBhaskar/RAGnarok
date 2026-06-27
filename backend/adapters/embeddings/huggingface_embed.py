"""
HuggingFace sentence-transformers embedding adapter.
Runs fully locally — no API key required, no quota limits.
Downloads model on first use (~90MB for all-MiniLM-L6-v2).
"""

from __future__ import annotations

import logging
from typing import Any

from backend.adapters.base import (
    AdapterUnavailableError,
    EmbeddingAdapter,
)
from backend.models.config import EmbeddingConfig

logger = logging.getLogger(__name__)


class HuggingFaceEmbeddingAdapter(EmbeddingAdapter):
    """
    Local embedding adapter using sentence-transformers.
    No API key needed. Model downloaded once and cached locally.

    Recommended models:
    - all-MiniLM-L6-v2      (fast, 384 dims, ~90MB)
    - all-mpnet-base-v2     (better quality, 768 dims, ~420MB)
    - BAAI/bge-small-en-v1.5 (best quality/speed tradeoff, 384 dims)
    """

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            ) from e

        model_id = self._config.model_id
        device = self._config.device or "cpu"

        logger.info(
            "HuggingFaceEmbeddingAdapter: loading model '%s' on %s "
            "(first load downloads ~90MB, subsequent loads are instant)",
            model_id, device,
        )

        try:
            self._model = SentenceTransformer(model_id, device=device)
            logger.info("HuggingFaceEmbeddingAdapter: model loaded successfully")
            return self._model
        except Exception as e:
            raise AdapterUnavailableError(
                "huggingface", "load_model",
                f"Failed to load model '{model_id}': {e}"
            ) from e

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode texts locally. Runs synchronously (CPU-bound)."""
        model = self._get_model()
        try:
            import asyncio
            # Run in thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
            )
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            raise AdapterUnavailableError("huggingface", "encode", str(e)) from e

    async def health_check(self) -> bool:
        try:
            await self.embed_query("health check")
            return True
        except Exception as e:
            logger.warning("HuggingFaceEmbeddingAdapter health check failed: %s", e)
            return False

    @property
    def model_id(self) -> str:
        return self._config.model_id

    @property
    def provider_name(self) -> str:
        return "huggingface"

    @property
    def dimensions(self) -> int | None:
        KNOWN_DIMS = {
            "all-MiniLM-L6-v2": 384,
            "all-mpnet-base-v2": 768,
            "BAAI/bge-small-en-v1.5": 384,
            "BAAI/bge-large-en-v1.5": 1024,
        }
        return KNOWN_DIMS.get(self._config.model_id)