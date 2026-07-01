"""
Chroma vector database retrieval adapter.
Supports both local (persist_directory) and HTTP (host/port) modes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.adapters.base import (
    AdapterAuthError,
    AdapterUnavailableError,
    RetrieverAdapter,
)
from backend.models.config import VectorDBConfig

logger = logging.getLogger(__name__)


class ChromaAdapter(RetrieverAdapter):
    """Retrieval adapter for ChromaDB."""

    def __init__(self, config: VectorDBConfig) -> None:
        self._config = config
        self._client: Any = None
        self._collection: Any = None

    async def _ensure_client(self) -> None:
        """Lazy-initialize Chroma client on first use.

        The chromadb SDK is fully synchronous. Constructing the client and
        fetching the collection both perform blocking network I/O, so this
        runs on a worker thread via run_in_executor to avoid stalling the
        asyncio event loop (and therefore every other concurrent request —
        including unrelated sessions' SSE streams and health checks).
        """
        if self._client is not None:
            return

        try:
            import chromadb
        except ImportError as e:
            raise ImportError(
                "chromadb is not installed. Run: pip install rag-debugger[chroma]"
            ) from e

        cfg = self._config

        def _connect() -> tuple[Any, Any]:
            if cfg.persist_directory:
                client = chromadb.PersistentClient(path=cfg.persist_directory)
                logger.debug("ChromaAdapter: connected to local client at %s", cfg.persist_directory)
            else:
                host = cfg.host or "localhost"
                port = cfg.port or 8000
                client = chromadb.HttpClient(host=host, port=port)
                logger.debug("ChromaAdapter: connected to HTTP client at %s:%s", host, port)

            collection = client.get_collection(name=cfg.collection_name)
            logger.debug("ChromaAdapter: using collection '%s'", cfg.collection_name)
            return client, collection

        try:
            loop = asyncio.get_event_loop()
            self._client, self._collection = await loop.run_in_executor(None, _connect)

        except Exception as e:
            err_str = str(e).lower()
            if "refused" in err_str or "timeout" in err_str or "connect" in err_str:
                raise AdapterUnavailableError("chroma", "connect", str(e)) from e
            if "does not exist" in err_str or "not found" in err_str:
                raise AdapterAuthError(
                    "chroma",
                    "get_collection",
                    f"Collection '{cfg.collection_name}' not found. "
                    f"Available collections: check your Chroma instance.",
                ) from e
            raise

    async def retrieve(
        self,
        query_embedding: list[float],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Query Chroma by embedding vector and return top_k results."""
        await self._ensure_client()

        def _query() -> Any:
            return self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, _query)
        except Exception as e:
            raise AdapterUnavailableError("chroma", "query", str(e)) from e

        chunks: list[dict[str, Any]] = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        for doc, meta, dist, chunk_id in zip(documents, metadatas, distances, ids):
            # Chroma returns L2 distance; convert to cosine similarity proxy
            # For normalized vectors: cosine_sim = 1 - (distance / 2)
            cosine_score = max(0.0, 1.0 - (dist / 2.0))

            if score_threshold is not None and cosine_score < score_threshold:
                continue

            chunks.append({
                "chunk_id": chunk_id,
                "text": doc,
                "score": cosine_score,
                "metadata": meta or {},
            })

        return chunks

    async def health_check(self) -> bool:
        """Check if Chroma is reachable and collection exists."""
        try:
            await self._ensure_client()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._collection.count)
            return True
        except Exception as e:
            logger.warning("ChromaAdapter health check failed: %s", e)
            return False

    async def get_corpus_chunks(self, limit: int = 100_000) -> list[dict[str, Any]]:
        """Fetch all chunks for BM25 oracle indexing."""
        await self._ensure_client()

        def _fetch() -> Any:
            total = self._collection.count()
            fetch_limit = min(total, limit)
            return total, self._collection.get(
                limit=fetch_limit,
                include=["documents", "metadatas"],
            )

        try:
            loop = asyncio.get_event_loop()
            total, results = await loop.run_in_executor(None, _fetch)

            chunks: list[dict[str, Any]] = []
            documents = results.get("documents", [])
            metadatas = results.get("metadatas", [])
            ids = results.get("ids", [])

            for doc, meta, chunk_id in zip(documents, metadatas, ids):
                if doc:  # skip empty documents
                    chunks.append({
                        "chunk_id": chunk_id,
                        "text": doc,
                        "metadata": meta or {},
                    })

            logger.info(
                "ChromaAdapter: fetched %d/%d corpus chunks for BM25 indexing",
                len(chunks),
                total,
            )
            return chunks

        except Exception as e:
            raise AdapterUnavailableError("chroma", "get_corpus", str(e)) from e

    @property
    def provider_name(self) -> str:
        return "chroma"
