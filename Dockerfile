# ── Stage 1: Frontend build ───────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --silent

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend ────────────────────────────────────────────────────
FROM python:3.11-slim AS backend

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[huggingface,chroma]" \
    && pip install --no-cache-dir groq

# Copy backend source
COPY backend/ ./backend/
COPY conftest.py pytest.ini ./

# Copy built frontend into backend static directory
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Pre-download HuggingFace model so container starts instantly
# (cached at /root/.cache/huggingface)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" \
    || echo "Model download failed — will download on first use"

# Create data directory for SQLite
RUN mkdir -p /data
ENV RAG_DEBUGGER_HOME=/data
ENV RAG_DEBUGGER_LOG_LEVEL=INFO

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8765"]