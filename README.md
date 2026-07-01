# RAGnarok
RAGnarok: The End of Hallucinations . An RAG Failure Attribution  &amp;  Quality Debugger

> Automated diagnostic tool for RAG pipeline failure attribution — built for ML/AI engineers.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com)

## What it does

RAGnarok answers one question: **when your RAG pipeline returns a wrong answer, is it the retrieval layer or the generation layer that failed?**

It does this through **oracle injection testing**: retrieving the best possible context via a BM25 oracle (completely independent of your vector DB) and injecting it into your LLM. If the LLM succeeds with oracle context but fails with retrieved context → retrieval failure. If it fails with both → generation failure.

```
Your Query
    │
    ├──► Vector DB Retrieval ──► Cosine Similarity Scoring ──► Retrieval Verdict
    │
    └──► BM25 Oracle Retrieval ──► LLM Generation ──► Generation Verdict
                                                              │
                                                    Compound Classifier
                                                              │
                                              Final Diagnosis + Recommendations
```

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Add OPENAI_API_KEY to .env

# Validate your pipeline config
rag-debug validate --config examples/pipeline.yaml

# Run diagnosis
rag-debug run \
  --config tests/golden_set/sample_pipeline.yaml \
  --queries tests/golden_set/sample_queries.json \
  --output report.md

# Run the quickstart demo (no real API needed)
python examples/quickstart.py
```

## Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | FastAPI + SSE | REST API with real-time streaming |
| CLI | Typer + Rich | `rag-debug` command |
| Retrieval Adapter | Abstract base + Chroma/Pinecone/Qdrant | Pluggable vector DB retrieval |
| Embedding Adapter | Abstract base + OpenAI/Cohere/HuggingFace | Pluggable embedding models |
| BM25 Oracle | rank-bm25 | Retrieval-method-independent oracle |
| Similarity Scoring | numpy + per-model thresholds | Calibrated relevance classification |
| Compound Classifier | Decision matrix | Retrieval × Generation → Final diagnosis |
| Recommendation Engine | Rule-based decision tree | Ranked, actionable recommendations |
| Database | SQLite (SQLAlchemy async) | Session persistence |
| Security | Secret scrubber + PII redactor + Pickle detector | Data safety |

## Supported Providers

**Vector Databases:** ChromaDB. *(Pinecone and Qdrant are defined in the config schema and validated, but have no adapter implementation yet — configuring them will raise a clear `ValueError` at session-creation time, not a silent failure.)*

**Embeddings:** OpenAI (text-embedding-3-small/large, ada-002), HuggingFace sentence-transformers (local, no API key required). *(Cohere is schema-defined but not yet implemented.)*

**LLMs:** OpenAI (GPT-4o-mini, GPT-4o), Groq (Llama 3.3, free tier). *(Anthropic and Ollama are schema-defined but not yet implemented.)*

Implementing a new provider means writing one adapter class against the interfaces in `backend/adapters/base.py` — see the existing Chroma/OpenAI/HuggingFace/Groq adapters for the pattern. PRs welcome.

## Pipeline Config

```yaml
name: "My RAG Pipeline"

vector_db:
  provider: chroma
  collection_name: my_docs
  host: localhost
  port: 8000

embedding:
  provider: openai
  model_id: text-embedding-3-small

llm:
  provider: openai
  model_id: gpt-4o-mini
  temperature: 0.0

retrieval:
  top_k: 5

prompt:
  template: |
    Context: {context}
    Question: {question}
    Answer:
```

## Diagnosis Modes

**Supervised** (recommended): Provide `expected_answer` in queries. Enables lexical overlap scoring and higher-confidence classification.

**Unsupervised**: Queries without expected answers. Uses heuristic quality scoring. Lower confidence, still useful for pattern detection.

## Security

- API keys are **never logged, stored, or included in reports** (secret scrubber applied globally)
- **Pickle format rejected** at all input surfaces (arbitrary code execution prevention)
- Optional `--redact-pii` flag strips emails, phone numbers, SSNs, Aadhaar, PAN cards from chunks before any LLM calls
- LLM judge (external data sharing) requires explicit `llm_judge_acknowledged: true` in config
- **No authentication by default.** RAGnarok is designed as a local tool bound to `127.0.0.1` — fine for solo use, but the same app is what `docker-compose.yml` starts bound to `0.0.0.0:8765`. If you deploy it anywhere reachable beyond your own machine, set `RAG_DEBUGGER_API_KEY` (every `/v1/*` request then requires a matching `X-API-Key` header) or put it behind your own auth proxy. The server logs a warning on startup if it's bound off-localhost with no API key set.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint + type check
ruff check .
mypy backend/

# Security scan
bandit -r backend/
detect-secrets scan

# Run API server (dev mode)
rag-debug serve --reload
```

## Project Structure

```
rag-debugger/
├── backend/
│   ├── adapters/          # Pluggable provider adapters
│   │   ├── retrievers/    # Vector DB adapters
│   │   ├── embeddings/    # Embedding model adapters
│   │   └── llms/          # LLM adapters
│   ├── core/              # Diagnostic engines
│   │   ├── bm25_engine.py
│   │   ├── retrieval_diagnostics.py
│   │   ├── generation_diagnostics.py
│   │   ├── compound_classifier.py
│   │   ├── similarity_scorer.py
│   │   ├── threshold_calibrator.py
│   │   └── recommendation_engine.py
│   ├── api/routes/        # FastAPI endpoints
│   ├── db/                # ORM models + migrations
│   ├── models/            # Pydantic schemas
│   ├── security/          # Secret scrubber, PII redactor, pickle detector
│   ├── services/          # Session + report orchestration
│   ├── cli.py             # Typer CLI
│   ├── config.py          # App settings
│   └── main.py            # FastAPI app factory
├── tests/
│   ├── unit/core/         # Core engine unit tests
│   ├── unit/security/     # Security unit tests
│   ├── api/               # API integration tests
│   └── golden_set/        # Sample configs and queries
├── examples/
│   └── quickstart.py
└── pyproject.toml
```

## Roadmap

- [x] React dashboard UI (`frontend/`), served automatically by the Docker image
- [x] Docker Compose (bundles a Chroma sidecar)
- [ ] Pinecone + Qdrant vector DB adapters
- [ ] Anthropic + Ollama + Cohere adapters
- [ ] Alembic migrations (dependency is installed; schema currently uses `create_all` — fine for local/dev use, not yet safe for in-place upgrades)
- [ ] RAGAS evaluator integration
- [ ] Pattern-level analysis across a query batch (beyond per-query diagnosis)
- [ ] API key authentication for non-localhost deployments

---

Built by [Prakruti Bhaskar](https://github.com/PrakrutiBhaskar) · BMSCE CS '28
