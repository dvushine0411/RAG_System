# rag_engine/Dockerfile — Python FastAPI RAG Engine
# Single-stage build (Python không có tree-shaking như JS)

FROM python:3.11-slim AS base
WORKDIR /app

# ── System Dependencies ────────────────────────────────────────────
# libgomp1: OpenMP runtime cần cho ONNX Runtime reranker
# poppler-utils: pdftotext fallback cho pdf-parse
# curl: healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python Dependencies ────────────────────────────────────────────
# Copy requirements trước để tận dụng Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Application Source ─────────────────────────────────────────────
COPY . .

# Chạy với user non-root (bảo mật)
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

# PYTHONPATH=/app đảm bảo Python resolve absolute imports đúng
# khi uvicorn chạy 'api.main:app' từ /app (rag_engine root)
ENV PYTHONPATH=/app

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -sf http://localhost:8000/health || exit 1

# Uvicorn với 2 workers — tăng lên theo CPU khi scale
CMD ["uvicorn", "api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
