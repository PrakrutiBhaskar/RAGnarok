"""
Report service — builds structured DiagnosisReport and renders Markdown.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.orm_models import DiagnosisSessionORM, QueryDiagnosisORM, RecommendationORM
from backend.models.report import DiagnosisReport, ReportSummary
from backend.models.session import (
    ChunkEvidence,
    QueryDiagnosisResult,
    Recommendation,
)

logger = logging.getLogger(__name__)

_EFFORT_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🔴"}
_IMPACT_EMOJI = {"low": "📉", "medium": "📊", "high": "📈"}
_DIAGNOSIS_LABELS = {
    "retrieval_failure":     "🔍 Retrieval Failure",
    "generation_failure":    "🤖 Generation Failure",
    "compound_failure":      "⚠️  Compound Failure",
    "data_quality_failure":  "📄 Data Quality Failure",
    "no_failure_detected":   "✅ No Failure Detected",
    "insufficient_evidence": "❓ Insufficient Evidence",
}


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def build_report(self, session: DiagnosisSessionORM) -> DiagnosisReport:
        """Build a complete DiagnosisReport from a loaded ORM session."""
        query_diagnoses = [
            self._orm_to_query_diagnosis(qd)
            for qd in sorted(session.query_diagnoses, key=lambda q: q.created_at)
        ]
        recommendations = [
            self._orm_to_recommendation(r)
            for r in sorted(session.recommendations, key=lambda r: r.rank)
        ]

        # Compute failure distribution
        dist: dict[str, int] = {}
        for qd in query_diagnoses:
            dist[qd.final_diagnosis] = dist.get(qd.final_diagnosis, 0) + 1

        dominant = max(dist, key=lambda k: dist[k]) if dist else None
        low_conf_count = sum(1 for qd in query_diagnoses if qd.confidence_score < 0.5)

        summary = ReportSummary(
            total_queries=len(query_diagnoses),
            failure_distribution=dist,
            dominant_failure=dominant,
            overall_confidence=session.overall_confidence,
            mode=session.mode,
            low_confidence_count=low_conf_count,
        )

        config_snapshot = session.pipeline_config_snapshot or {}
        pipeline_name = config_snapshot.get("name", f"Session {session.id[:8]}")

        return DiagnosisReport(
            session_id=session.id,
            pipeline_name=pipeline_name,
            generated_at=datetime.utcnow(),
            status=session.status,
            summary=summary,
            query_diagnoses=query_diagnoses,
            recommendations=recommendations,
            pipeline_snapshot=config_snapshot,
            low_confidence_flag=low_conf_count > 0,
        )

    def render_markdown(self, report: DiagnosisReport) -> str:
        """Render a DiagnosisReport to Markdown."""
        lines: list[str] = []
        s = report.summary

        # Header
        lines += [
            f"# RAG Debugger Report — {report.pipeline_name}",
            f"",
            f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
            f"**Session ID:** `{report.session_id}`  ",
            f"**Status:** {report.status}  ",
            f"**Mode:** {s.mode}",
            f"",
            f"---",
            f"",
            f"## Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Queries | {s.total_queries} |",
            f"| Dominant Failure | {_DIAGNOSIS_LABELS.get(str(s.dominant_failure), str(s.dominant_failure))} |",
            f"| Overall Confidence | {f'{s.overall_confidence:.0%}' if s.overall_confidence else 'N/A'} |",
            f"| Low-Confidence Queries | {s.low_confidence_count} |",
            f"",
            f"### Failure Distribution",
            f"",
        ]

        for diagnosis, count in sorted(s.failure_distribution.items(), key=lambda x: -x[1]):
            label = _DIAGNOSIS_LABELS.get(diagnosis, diagnosis)
            pct = count / s.total_queries * 100 if s.total_queries else 0
            lines.append(f"- {label}: **{count}** ({pct:.0f}%)")

        lines += ["", "---", "", "## Recommendations", ""]

        if report.recommendations:
            for rec in report.recommendations:
                effort_e = _EFFORT_EMOJI.get(rec.effort, "")
                impact_e = _IMPACT_EMOJI.get(rec.impact, "")
                lines += [
                    f"### {rec.rank}. {rec.title}",
                    f"",
                    f"**Effort:** {effort_e} {rec.effort.capitalize()} | **Impact:** {impact_e} {rec.impact.capitalize()}",
                    f"",
                    rec.description,
                    f"",
                ]
                if rec.code_snippet:
                    lines += [
                        "```python",
                        rec.code_snippet,
                        "```",
                        "",
                    ]
        else:
            lines.append("_No recommendations generated for this session._\n")

        lines += ["---", "", "## Query Diagnoses", ""]

        for i, qd in enumerate(report.query_diagnoses, 1):
            conf_pct = f"{qd.confidence_score:.0%}"
            diag_label = _DIAGNOSIS_LABELS.get(qd.final_diagnosis, qd.final_diagnosis)
            lines += [
                f"### Query {i}",
                f"",
                f"> {qd.query_text}",
                f"",
                f"| Field | Value |",
                f"|-------|-------|",
                f"| Diagnosis | {diag_label} |",
                f"| Confidence | {conf_pct} |",
                f"| Retrieval Verdict | `{qd.retrieval_verdict}` |",
                f"| Generation Verdict | `{qd.generation_verdict}` |",
            ]
            if qd.max_cosine_similarity is not None:
                lines.append(f"| Max Cosine Similarity | {qd.max_cosine_similarity:.4f} |")
            if qd.bm25_score is not None:
                lines.append(f"| BM25 Oracle Score | {qd.bm25_score:.4f} |")
            if qd.expected_answer_in_corpus is not None:
                lines.append(f"| Answer in Corpus | {'Yes' if qd.expected_answer_in_corpus else 'No'} |")

            if qd.expected_answer:
                lines += ["", f"**Expected:** {qd.expected_answer[:200]}"]
            if qd.actual_answer:
                lines += [f"**Actual:** {qd.actual_answer[:200]}"]

            if qd.confidence_score < 0.5:
                lines += [
                    "",
                    "> ⚠️ **Low confidence** — diagnosis may be unreliable. "
                    "Consider providing expected_answer for supervised mode.",
                ]

            lines.append("")

        lines += [
            "---",
            "",
            f"_Generated by RAG Debugger v1.0 · https://github.com/PrakrutiBhaskar/rag-debugger_",
        ]

        return "\n".join(lines)

    # ── ORM → Pydantic converters ─────────────────────────────────────────────

    def _orm_to_query_diagnosis(self, orm: QueryDiagnosisORM) -> QueryDiagnosisResult:
        from uuid import UUID

        retrieved = [
            ChunkEvidence(**c) if isinstance(c, dict) else c
            for c in (orm.retrieved_chunks or [])
        ]
        oracle = [
            ChunkEvidence(**c) if isinstance(c, dict) else c
            for c in (orm.oracle_chunks or [])
        ]

        return QueryDiagnosisResult(
            id=UUID(orm.id),
            session_id=UUID(orm.session_id),
            query_text=orm.query_text,
            expected_answer=orm.expected_answer,
            actual_answer=orm.actual_answer,
            retrieved_chunks=retrieved,
            oracle_chunks=oracle,
            retrieval_verdict=orm.retrieval_verdict,
            generation_verdict=orm.generation_verdict,
            final_diagnosis=orm.final_diagnosis,
            confidence_score=orm.confidence_score,
            max_cosine_similarity=orm.max_cosine_similarity,
            avg_cosine_similarity=orm.avg_cosine_similarity,
            bm25_score=orm.bm25_score,
            expected_answer_in_corpus=orm.expected_answer_in_corpus,
            evidence=orm.evidence or {},
            created_at=orm.created_at,
        )

    def _orm_to_recommendation(self, orm: RecommendationORM) -> Recommendation:
        from uuid import UUID

        return Recommendation(
            id=UUID(orm.id),
            session_id=UUID(orm.session_id),
            diagnosis_type=orm.diagnosis_type,
            title=orm.title,
            description=orm.description,
            effort=orm.effort,
            impact=orm.impact,
            code_snippet=orm.code_snippet,
            rank=orm.rank,
            impact_score=orm.impact_score,
            effort_score=orm.effort_score,
            created_at=orm.created_at,
        )
