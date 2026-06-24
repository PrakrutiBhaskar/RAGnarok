"""
RAG Debugger — Quickstart Example
Run with: python examples/quickstart.py

This example demonstrates the diagnostic API without a real vector DB.
It uses a mock adapter that simulates retrieval failures.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from backend.core.bm25_engine import BM25Engine
from backend.core.compound_classifier import CompoundClassifier
from backend.core.generation_diagnostics import GenerationDiagnosticEngine
from backend.core.recommendation_engine import RecommendationEngine
from backend.core.retrieval_diagnostics import RetrievalDiagnosticEngine
from backend.models.config import (
    ChunkingConfig, EmbeddingConfig, LLMConfig, PipelineConfig,
    PromptConfig, RetrievalConfig, VectorDBConfig,
)

# ── Corpus for BM25 oracle ────────────────────────────────────────────────────
CORPUS = [
    {
        "chunk_id": "doc1_chunk1",
        "text": "To reset your password, go to Settings > Security > Reset Password. "
                "You will receive an email with a reset link valid for 24 hours.",
        "metadata": {"source": "help_center", "doc_id": "doc1"},
    },
    {
        "chunk_id": "doc1_chunk2",
        "text": "Annual subscriptions are eligible for a full refund within 30 days of purchase. "
                "Monthly subscriptions can be cancelled anytime with no refund for the current period.",
        "metadata": {"source": "help_center", "doc_id": "doc2"},
    },
    {
        "chunk_id": "doc2_chunk1",
        "text": "API rate limits for the free tier: 100 calls per day, 10 requests per minute. "
                "Pro tier: 10,000 calls per day, 100 requests per minute.",
        "metadata": {"source": "api_docs", "doc_id": "doc3"},
    },
]

# ── Failing queries ────────────────────────────────────────────────────────────
FAILING_QUERIES = [
    {
        "query": "How do I reset my password?",
        "expected_answer": "Go to Settings > Security > Reset Password. You receive an email link valid for 24 hours.",
        "actual_answer": "I don't have information about this.",
    },
    {
        "query": "What are the API rate limits for the free tier?",
        "expected_answer": "Free tier: 100 calls per day, 10 requests per minute.",
        "actual_answer": "Rate limits vary by plan.",
    },
]


async def main() -> None:
    print("=" * 60)
    print("RAG Debugger — Quickstart Demo")
    print("=" * 60)

    # Build config
    config = PipelineConfig(
        name="Demo Pipeline",
        vector_db=VectorDBConfig(provider="chroma", collection_name="demo"),
        embedding=EmbeddingConfig(provider="openai", model_id="text-embedding-3-small"),
        llm=LLMConfig(provider="openai", model_id="gpt-4o-mini"),
        retrieval=RetrievalConfig(top_k=3),
        chunking=ChunkingConfig(chunk_size=512, chunk_overlap=64),
        prompt=PromptConfig(
            template="Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        ),
    )
    print(f"\n✓ Config: {config.name}")
    print(f"  Fingerprint: {config.fingerprint()[:16]}...")

    # Mock adapters (no real API calls in quickstart)
    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = [
        # Simulate low-quality retrieval — wrong chunks returned
        {"chunk_id": "unrelated_1", "text": "The weather today is sunny.", "score": 0.15, "metadata": {}},
        {"chunk_id": "unrelated_2", "text": "Python was created by Guido van Rossum.", "score": 0.12, "metadata": {}},
    ]
    mock_retriever.get_corpus_chunks.return_value = CORPUS
    mock_retriever.provider_name = "chroma"

    mock_embedder = AsyncMock()
    mock_embedder.embed_query.return_value = [0.1] * 1536
    mock_embedder.model_id = "text-embedding-3-small"
    mock_embedder.provider_name = "openai"

    mock_llm = AsyncMock()
    # Oracle injection returns a good answer — proving retrieval (not generation) is the problem
    mock_llm.generate.return_value = (
        "To reset your password, navigate to Settings > Security > Reset Password. "
        "A reset link will be emailed to you, valid for 24 hours."
    )

    # Build BM25 oracle
    print("\n✓ Building BM25 oracle index...")
    bm25 = BM25Engine()
    bm25.index(CORPUS)
    print(f"  Indexed {bm25.corpus_size} chunks")

    # Build engines
    retrieval_engine = RetrievalDiagnosticEngine(
        retriever=mock_retriever,
        embedder=mock_embedder,
        bm25_engine=bm25,
        top_k=3,
    )
    generation_engine = GenerationDiagnosticEngine(
        llm=mock_llm,
        prompt_config=config.prompt,
    )
    classifier = CompoundClassifier()

    print("\n" + "─" * 60)
    print("Running per-query diagnosis...")
    print("─" * 60)

    diagnoses = []
    for i, q in enumerate(FAILING_QUERIES):
        print(f"\nQuery {i+1}: {q['query']}")

        r_result = await retrieval_engine.diagnose(
            query=q["query"],
            expected_answer=q["expected_answer"],
        )
        g_result = await generation_engine.diagnose(
            query=q["query"],
            oracle_chunks=list(bm25.retrieve(q["query"], top_k=3)),
            actual_answer=q["actual_answer"],
            expected_answer=q["expected_answer"],
        )
        classification = classifier.classify(
            retrieval_verdict=r_result.verdict,
            generation_verdict=g_result.verdict,
            retrieval_confidence=r_result.confidence,
            generation_confidence=g_result.confidence,
            retrieval_evidence=r_result.evidence,
            generation_evidence=g_result.evidence,
        )

        print(f"  Retrieval:  {r_result.verdict} (conf={r_result.confidence:.0%})")
        print(f"  Generation: {g_result.verdict} (conf={g_result.confidence:.0%})")
        print(f"  Diagnosis:  {classification.final_diagnosis} (conf={classification.confidence_score:.0%})")
        diagnoses.append(classification)

    # Recommendations
    print("\n" + "─" * 60)
    rec_engine = RecommendationEngine()
    failure_dist = {}
    for d in diagnoses:
        failure_dist[d.final_diagnosis] = failure_dist.get(d.final_diagnosis, 0) + 1

    dominant = max(failure_dist, key=lambda k: failure_dist[k])
    import uuid
    recs = rec_engine.generate(
        session_id=uuid.uuid4(),
        dominant_failure=dominant,
        failure_distribution=failure_dist,
        session_evidence={},
    )

    print(f"\nDominant failure: {dominant}")
    print(f"Top recommendations ({len(recs)} total):\n")
    for rec in recs[:3]:
        print(f"  [{rec.rank}] {rec.title}")
        print(f"       Effort={rec.effort} | Impact={rec.impact}")

    print("\n" + "=" * 60)
    print("Demo complete. Run 'rag-debug run --config pipeline.yaml --queries queries.json' for real diagnosis.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
