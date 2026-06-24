"""
POST /v1/validate/pipeline — validate a pipeline config without running a full session.
First endpoint to build (Phase 1 per implementation blueprint).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.models.config import PipelineConfig, QueryBatch

router = APIRouter()


@router.post("/validate/pipeline")
async def validate_pipeline(body: dict[str, Any]) -> JSONResponse:
    """
    Validate a pipeline config (YAML parsed to JSON).
    Returns validation errors with field-level detail if invalid.
    Does NOT connect to any external service.
    """
    try:
        config = PipelineConfig(**body)
        return JSONResponse({
            "valid": True,
            "pipeline_name": config.name,
            "fingerprint": config.fingerprint(),
            "providers": {
                "vector_db": config.vector_db.provider,
                "embedding": config.embedding.provider,
                "llm": config.llm.provider,
            },
            "warnings": _collect_warnings(config),
        })
    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={
                "valid": False,
                "errors": e.errors(include_url=False),
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"valid": False, "errors": [{"msg": str(e)}]},
        )


@router.post("/validate/queries")
async def validate_queries(body: dict[str, Any]) -> JSONResponse:
    """
    Validate a query batch (JSON array of query objects).
    """
    try:
        batch = QueryBatch(**body)
        supervised = batch.is_supervised
        return JSONResponse({
            "valid": True,
            "query_count": len(batch.queries),
            "mode": "supervised" if supervised else "unsupervised",
            "warnings": _query_warnings(batch),
        })
    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={"valid": False, "errors": e.errors(include_url=False)},
        )


def _collect_warnings(config: PipelineConfig) -> list[str]:
    warnings: list[str] = []
    if not config.prompt:
        warnings.append(
            "No prompt_config provided. Generation diagnostics will be skipped. "
            "Add a prompt config to enable oracle injection testing."
        )
    if config.retrieval.top_k < 3:
        warnings.append(
            f"top_k={config.retrieval.top_k} is very low. "
            "Retrieval diagnostics are more reliable with top_k >= 5."
        )
    if config.enable_llm_judge and not config.llm_judge_acknowledged:
        warnings.append(
            "enable_llm_judge=True but llm_judge_acknowledged=False. "
            "LLM judge will be disabled."
        )
    return warnings


def _query_warnings(batch: QueryBatch) -> list[str]:
    warnings: list[str] = []
    if len(batch.queries) < 3:
        warnings.append(
            f"Only {len(batch.queries)} queries provided. "
            "Pattern-level recommendations require at least 3 queries."
        )
    supervised_count = sum(1 for q in batch.queries if q.expected_answer)
    if supervised_count > 0 and supervised_count < len(batch.queries):
        warnings.append(
            f"Mixed mode: {supervised_count}/{len(batch.queries)} queries have expected_answer. "
            "Queries without expected answers will run in unsupervised mode."
        )
    return warnings
