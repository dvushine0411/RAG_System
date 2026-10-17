"""
System Role: FastAPI route handlers exposing vector similarity retrieval and cross-encoder reranking endpoints.
Inputs: RetrievalQueryRequest payloads specifying search query, metadata filters, and HNSW parameters.
Outputs: RetrievalResponse JSON payload containing ranked ScoredChunkDTO list.
Ref: ARCHITECTURE.md §2.2 Phase B, §5.2 Directory Dictionary
"""

import logging
from fastapi import APIRouter, HTTPException, status

from schemas.retrieval import RetrievalQueryRequest, RetrievalResponse
from retrieval.retriever import VectorRetriever

logger = logging.getLogger("rag_engine.api.retrieval")

router = APIRouter(prefix="/api/v1/retrieval", tags=["Retrieval"])
retriever_instance = VectorRetriever()


@router.post(
    "/search",
    response_model=RetrievalResponse,
    status_code=status.HTTP_200_OK,
    summary="Vector similarity search with HNSW tuning and Cross-Encoder reranking",
)
async def search_and_rerank(request: RetrievalQueryRequest) -> RetrievalResponse:
    """
    Executes Phase 4 two-stage retrieval:
    1. Embed query into vector space.
    2. HNSW ANN search in Qdrant with optional metadata filtering and ef_search parameter.
    3. Cross-Encoder reranking to score Top-K candidates into Top-N.
    4. Graceful fallback on reranker failure or empty match.
    """
    try:
        response = await retriever_instance.retrieve_and_rerank(request)
        return response
    except Exception as exc:
        logger.error(f"Retrieval pipeline error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval engine failed: {str(exc)}",
        )
