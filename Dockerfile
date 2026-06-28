# ── Stage 1: Frontend build ───────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --silent

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.11-slim AS backend

# System deps — curl is required for the HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── STEP 1: Install CPU-only PyTorch BEFORE everything else ───────────────────
# If this runs after sentence-transformers, pip resolves the GPU build of torch
# (~1.5 GB of CUDA libs) and produces hash-mismatch errors on NVIDIA packages.
# Pinning the CPU wheel here prevents that entirely.
# torch 2.4+ required by sentence-transformers 3.0+
RUN pip install --no-cache-dir --retries 3 \
    torch==2.4.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# ── STEP 2: Install all project deps (layer-cached until pyproject.toml changes)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --retries 3 -e ".[huggingface,chroma]" \
    && pip install --no-cache-dir --retries 3 groq

# ── STEP 3: Copy application source ──────────────────────────────────────────
COPY backend/ ./backend/
COPY conftest.py pytest.ini ./

# ── STEP 4: Copy built React app (served as static files by FastAPI) ──────────
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# ── STEP 5: Pre-download the HuggingFace embedding model ─────────────────────
# Bakes the model into the image so the first request is instant.
# The || echo means a network-less build environment won't fail the build.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')" \
    || echo "Model download failed — will download on first use"

# ── Data directory for SQLite DB ──────────────────────────────────────────────
RUN mkdir -p /data

# ── Environment defaults (all overridable via docker-compose / .env) ──────────
ENV RAG_DEBUGGER_HOME=/data \
    RAG_DEBUGGER_LOG_LEVEL=INFO \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8765

# start-period gives Uvicorn + DB init time before Docker starts counting retries
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

# workers=1 is required — the in-memory SSE event queue in stream.py is not
# safe across multiple processes. If you add Redis pub/sub later, bump this.
CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8765", \
     "--workers", "1"]