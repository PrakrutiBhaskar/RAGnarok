"""
Recommendation engine — decision tree that maps failure diagnoses to ranked, actionable recommendations.
Each recommendation includes: title, description, effort, impact, and a code snippet or config diff.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from backend.models.session import FinalDiagnosis, Recommendation

logger = logging.getLogger(__name__)


@dataclass
class RecommendationTemplate:
    title: str
    description: str
    effort: str          # "low" | "medium" | "high"
    impact: str          # "low" | "medium" | "high"
    impact_score: float  # 0.0–1.0
    effort_score: float  # 0.0–1.0
    code_snippet: str | None = None


# ── Recommendation library ────────────────────────────────────────────────────

_RETRIEVAL_FAILURE_RECS: list[RecommendationTemplate] = [
    RecommendationTemplate(
        title="Increase top_k to retrieve more candidate chunks",
        description=(
            "Your pipeline retrieves too few chunks, missing relevant context. "
            "Increasing top_k gives the LLM more material to synthesize from. "
            "Start with 2–3x your current value and evaluate impact on answer quality."
        ),
        effort="low",
        impact="high",
        impact_score=0.85,
        effort_score=0.10,
        code_snippet=(
            "# In your pipeline config (pipeline.yaml):\n"
            "retrieval:\n"
            "  top_k: 10  # was 5\n\n"
            "# Or in code:\n"
            "retriever.search(query, k=10)"
        ),
    ),
    RecommendationTemplate(
        title="Upgrade to a higher-quality embedding model",
        description=(
            "Low cosine similarity scores suggest your embedding model is producing "
            "poorly aligned representations for your domain. Consider upgrading from "
            "text-embedding-ada-002 to text-embedding-3-small/large, or a domain-specific model."
        ),
        effort="medium",
        impact="high",
        impact_score=0.90,
        effort_score=0.50,
        code_snippet=(
            "# In pipeline.yaml:\n"
            "embedding:\n"
            "  provider: openai\n"
            "  model_id: text-embedding-3-large  # was ada-002\n\n"
            "# After changing embedding model, you MUST re-index your corpus.\n"
            "# Old embeddings are incompatible with the new model."
        ),
    ),
    RecommendationTemplate(
        title="Reduce chunk size for more precise retrieval",
        description=(
            "Large chunks dilute relevance signals. Each chunk should contain one "
            "coherent idea. Try reducing chunk size from 512 to 256 tokens, "
            "and re-index. Smaller chunks improve retrieval precision at the cost of "
            "potentially losing context — mitigate with chunk overlap."
        ),
        effort="medium",
        impact="high",
        impact_score=0.80,
        effort_score=0.55,
        code_snippet=(
            "from langchain.text_splitter import RecursiveCharacterTextSplitter\n\n"
            "splitter = RecursiveCharacterTextSplitter(\n"
            "    chunk_size=256,      # was 512\n"
            "    chunk_overlap=64,\n"
            "    separators=['\\n\\n', '\\n', '. ', ' '],\n"
            ")"
        ),
    ),
    RecommendationTemplate(
        title="Add metadata filters to narrow retrieval scope",
        description=(
            "If your corpus spans multiple topics/domains, unfiltered retrieval "
            "will return irrelevant chunks from unrelated sections. "
            "Add metadata filters (document_type, category, date_range) to scope "
            "retrieval to the relevant subset."
        ),
        effort="medium",
        impact="medium",
        impact_score=0.60,
        effort_score=0.45,
        code_snippet=(
            "# Chroma example:\n"
            "collection.query(\n"
            "    query_embeddings=[embedding],\n"
            "    n_results=10,\n"
            "    where={'document_type': 'technical_spec'},  # add filter\n"
            ")"
        ),
    ),
    RecommendationTemplate(
        title="Implement hybrid search (dense + sparse)",
        description=(
            "Pure vector search misses exact keyword matches. Hybrid search combines "
            "dense embedding retrieval with BM25 keyword retrieval, "
            "significantly improving recall for technical queries, product names, "
            "and domain-specific terminology."
        ),
        effort="high",
        impact="high",
        impact_score=0.88,
        effort_score=0.75,
        code_snippet=(
            "# Using LangChain EnsembleRetriever:\n"
            "from langchain.retrievers import BM25Retriever, EnsembleRetriever\n\n"
            "bm25_retriever = BM25Retriever.from_documents(docs)\n"
            "bm25_retriever.k = 5\n\n"
            "ensemble = EnsembleRetriever(\n"
            "    retrievers=[bm25_retriever, vector_retriever],\n"
            "    weights=[0.4, 0.6],\n"
            ")"
        ),
    ),
]

_GENERATION_FAILURE_RECS: list[RecommendationTemplate] = [
    RecommendationTemplate(
        title="Rewrite prompt to explicitly instruct citation of context",
        description=(
            "The LLM may be ignoring the provided context and hallucinating from "
            "pre-training knowledge. Add explicit instructions to ONLY use the "
            "provided context, and to say 'I don't know' if the answer is not in the context."
        ),
        effort="low",
        impact="high",
        impact_score=0.85,
        effort_score=0.10,
        code_snippet=(
            "SYSTEM_PROMPT = (\n"
            "    'You are a precise assistant. Answer ONLY using the provided context. '\n"
            "    'If the answer is not in the context, say: '\n"
            "    '\"I cannot find this information in the provided documents.\" '\n"
            "    'Do not use prior knowledge. Do not speculate.'\n"
            ")\n\n"
            "PROMPT_TEMPLATE = (\n"
            "    'Context:\\n{context}\\n\\n'\n"
            "    'Question: {question}\\n\\n'\n"
            "    'Answer (using only the context above):'\n"
            ")"
        ),
    ),
    RecommendationTemplate(
        title="Switch to a stronger LLM for synthesis",
        description=(
            "The current model may lack the reasoning capacity to synthesize "
            "answers from the retrieved context. Consider upgrading from gpt-3.5-turbo "
            "or a smaller local model to gpt-4o-mini or gpt-4o."
        ),
        effort="low",
        impact="high",
        impact_score=0.80,
        effort_score=0.15,
        code_snippet=(
            "# In pipeline.yaml:\n"
            "llm:\n"
            "  provider: openai\n"
            "  model_id: gpt-4o-mini  # was gpt-3.5-turbo\n"
            "  temperature: 0.0"
        ),
    ),
    RecommendationTemplate(
        title="Reduce context window noise: pass only top-K most relevant chunks",
        description=(
            "Passing too many chunks overwhelms the LLM's context window and "
            "causes it to ignore key information. Re-rank retrieved chunks by "
            "relevance and pass only the top 3–5 to the prompt."
        ),
        effort="medium",
        impact="medium",
        impact_score=0.65,
        effort_score=0.40,
        code_snippet=(
            "# Re-rank with a cross-encoder before generation:\n"
            "from sentence_transformers import CrossEncoder\n\n"
            "reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')\n"
            "scores = reranker.predict([(query, chunk.page_content) for chunk in chunks])\n"
            "ranked_chunks = [c for _, c in sorted(zip(scores, chunks), reverse=True)][:3]"
        ),
    ),
    RecommendationTemplate(
        title="Lower temperature to reduce hallucination",
        description=(
            "A non-zero temperature causes the LLM to introduce creative variation, "
            "which in RAG contexts manifests as hallucination. Set temperature=0.0 "
            "for factual QA tasks."
        ),
        effort="low",
        impact="medium",
        impact_score=0.55,
        effort_score=0.05,
        code_snippet=(
            "# In pipeline.yaml:\n"
            "llm:\n"
            "  temperature: 0.0  # was 0.7 or higher"
        ),
    ),
]

_DATA_QUALITY_FAILURE_RECS: list[RecommendationTemplate] = [
    RecommendationTemplate(
        title="Audit corpus for missing documents covering the failing query topics",
        description=(
            "The expected answers for failing queries cannot be found anywhere in your "
            "corpus. This is a data quality problem — no amount of retrieval or prompt "
            "tuning will fix it. Identify which topics/documents are missing and add them."
        ),
        effort="high",
        impact="high",
        impact_score=0.95,
        effort_score=0.80,
        code_snippet=(
            "# Identify missing topics using failing queries:\n"
            "from rag_debugger import analyze_corpus_gaps\n\n"
            "gaps = analyze_corpus_gaps(\n"
            "    failing_queries=failing_queries,\n"
            "    corpus=your_corpus,\n"
            ")\n"
            "print(gaps.missing_topics)"
        ),
    ),
    RecommendationTemplate(
        title="Review and improve document preprocessing pipeline",
        description=(
            "Corpus chunks may be malformed due to poor PDF extraction, HTML stripping, "
            "or encoding issues. Review a sample of chunks for garbled text, "
            "missing sentences, or encoding artifacts before re-indexing."
        ),
        effort="medium",
        impact="high",
        impact_score=0.80,
        effort_score=0.60,
        code_snippet=None,
    ),
]

_COMPOUND_FAILURE_RECS: list[RecommendationTemplate] = [
    RecommendationTemplate(
        title="Fix retrieval layer first, then re-evaluate generation",
        description=(
            "Both retrieval and generation are failing. Fix retrieval first (increase top_k, "
            "improve chunking, upgrade embedding model). Then re-run diagnosis — "
            "generation failures often resolve automatically once retrieval provides "
            "high-quality context."
        ),
        effort="medium",
        impact="high",
        impact_score=0.90,
        effort_score=0.50,
        code_snippet=None,
    ),
] + _RETRIEVAL_FAILURE_RECS[:2] + _GENERATION_FAILURE_RECS[:2]

_DIAGNOSIS_TO_RECS: dict[FinalDiagnosis, list[RecommendationTemplate]] = {
    "retrieval_failure":    _RETRIEVAL_FAILURE_RECS,
    "generation_failure":   _GENERATION_FAILURE_RECS,
    "data_quality_failure": _DATA_QUALITY_FAILURE_RECS,
    "compound_failure":     _COMPOUND_FAILURE_RECS,
    "no_failure_detected":  [],
    "insufficient_evidence": [],
}


class RecommendationEngine:
    """
    Produces ranked recommendations given a diagnosis type and session evidence.
    Recommendations are sorted by priority_score (impact / effort ratio).
    """

    def generate(
        self,
        session_id: UUID,
        dominant_failure: FinalDiagnosis | None,
        failure_distribution: dict[str, int],
        session_evidence: dict[str, Any],
    ) -> list[Recommendation]:
        """
        Generate ranked recommendations for a session.

        Args:
            session_id: Session UUID for FK reference.
            dominant_failure: Most common failure type across all queries.
            failure_distribution: Count of each failure type.
            session_evidence: Aggregated evidence from all query diagnoses.
        """
        if dominant_failure is None or dominant_failure == "insufficient_evidence":
            logger.info(
                "RecommendationEngine: no dominant failure — skipping recommendations"
            )
            return []

        templates = _DIAGNOSIS_TO_RECS.get(dominant_failure, [])
        if not templates:
            logger.info(
                "RecommendationEngine: no recommendations for '%s'", dominant_failure
            )
            return []

        recommendations: list[Recommendation] = []

        for i, template in enumerate(templates):
            rec = Recommendation(
                session_id=session_id,
                diagnosis_type=dominant_failure,
                title=template.title,
                description=template.description,
                effort=template.effort,          # type: ignore[arg-type]
                impact=template.impact,          # type: ignore[arg-type]
                code_snippet=template.code_snippet,
                rank=i + 1,  # temporary rank; will be re-ranked below
                impact_score=template.impact_score,
                effort_score=template.effort_score,
            )
            recommendations.append(rec)

        # Re-rank by priority_score (impact/effort ratio)
        recommendations.sort(key=lambda r: r.priority_score, reverse=True)
        for i, rec in enumerate(recommendations):
            rec.rank = i + 1

        logger.info(
            "RecommendationEngine: generated %d recommendations for '%s'",
            len(recommendations),
            dominant_failure,
        )
        return recommendations
