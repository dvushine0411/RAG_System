"""
System Role: FastAPI application entry point orchestrating ingestion, embedding, vector storage, and query pipelines.
Inputs: HTTP requests from Node.js API Gateway (multipart files, query payloads, vector maintenance triggers).
Outputs: JSON responses for ingestion status, embeddings, vector metadata, and future streaming tokens.
Ref: ARCHITECTURE.md §2.2 Phase A & Phase B
"""


from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import logging

from config import settings

# ─── Configure logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("rag_engine")


# ─── Lifespan: startup / shutdown hooks ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB connections and ML models on startup."""
    logger.info("🚀 RAG Engine starting up...")

    # Phase 3: Auto-provision Qdrant collection and HNSW index if reachable
    try:
        from vectordb.collection_manager import ensure_collection_exists
        await ensure_collection_exists()
        logger.info("✅ Qdrant collection verified and ready.")
    except Exception as exc:
        logger.warning(f"⚠️ Qdrant startup check deferred (will connect on demand): {exc}")

    # Phase 8: pre-build providers/HTTP clients so the first user query is not ~5 s slower
    try:
        from api.warmup import warm_up_providers
        warm_up_providers()
    except Exception as exc:
        logger.warning(f"⚠️ Provider warm-up skipped: {exc}")

    logger.info("✅ RAG Engine ready.")
    yield

    # Cleanup on shutdown
    logger.info("🛑 RAG Engine shutting down...")
    try:
        from vectordb.qdrant_client import close_qdrant_client
        await close_qdrant_client()
    except Exception as exc:
        logger.warning(f"Error during Qdrant client shutdown: {exc}")


# ─── FastAPI App ─────────────────────────────────────────────────────
app = FastAPI(
    title="RAG Engine",
    description="Python RAG pipeline: parsing, chunking, embedding, retrieval, reranking, generation",
    version="0.1.0",
    lifespan=lifespan
)

# CORS — chỉ cho phép Node.js API Gateway gọi vào
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://api:3000", "http://localhost:3000"],
    allow_methods=["POST", "GET", "DELETE"],
    allow_headers=["*"],
)


# ─── Include Routers ─────────────────────────────────────────────────
from api.routes.ingestion import router as ingestion_router
from api.routes.embeddings import router as embeddings_router
from api.routes.vectordb import router as vectordb_router
from api.routes.retrieval import router as retrieval_router
from api.routes.augmentation import router as augmentation_router
from api.routes.generation import router as generation_router, generate_stream_endpoint, query_stream_endpoint

app.include_router(ingestion_router)
app.include_router(embeddings_router)
app.include_router(vectordb_router)
app.include_router(retrieval_router)
app.include_router(augmentation_router)
app.include_router(generation_router)



# ─── Health Check ────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for Docker HEALTHCHECK."""
    return {"status": "ok", "service": "rag_engine"}


# ─── Retrieval Endpoint (Phase 4) ────────────────────────────────────
from schemas.retrieval import RetrievalQueryRequest, RetrievalResponse
from retrieval.retriever import VectorRetriever

retriever_service = VectorRetriever()


@app.post("/retrieve", response_model=RetrievalResponse, tags=["Retrieval"])
async def retrieve(request: RetrievalQueryRequest) -> RetrievalResponse:
    """
    Execute retrieval pipeline (Phase 4):
    Dense HNSW vector search -> metadata filtering -> cross-encoder reranking -> graceful fallback.
    Ref: ARCHITECTURE.md §2.2 Phase B & eval_vector_search skill
    """
    return await retriever_service.retrieve_and_rerank(request)


# ─── Generation Endpoint (Phase 6) ───────────────────────────────────
from schemas.generation import GenerateStreamRequest, QueryStreamRequest


@app.post("/generate", tags=["Generation"])
async def generate(request: GenerateStreamRequest):
    """
    Run LLM generation with Server-Sent Events (SSE) streaming.
    Ref: ARCHITECTURE.md §2.2 Phase B step 6-7, Phase 6
    """
    return await generate_stream_endpoint(request)


# ─── Query (Full Pipeline) Endpoint (Phase 6) ────────────────────────
@app.post("/query", tags=["Pipeline"])
async def full_pipeline_query(request: QueryStreamRequest):
    """
    Execute the complete RAG pipeline end-to-end with SSE streaming:
    Embed query → Retrieve → Rerank → Augment → Stream LLM with citations.
    Ref: ARCHITECTURE.md §2.2 Phase B step 1-7, Phase 6
    """
    return await query_stream_endpoint(request)
