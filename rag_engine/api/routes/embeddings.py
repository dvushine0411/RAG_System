"""
System Role: FastAPI router exposing batch embedding generation endpoints.
Inputs: Raw text chunk lists received via HTTP POST.
Outputs: Generated 1536-dimensional dense embedding vectors.
Ref: ARCHITECTURE.md §2.2 Phase A & §5
"""

import logging
from fastapi import APIRouter, HTTPException, status

from config import settings
from embeddings.factory import get_embedding_provider
from schemas.embedding import EmbeddingItem, EmbeddingRequest, EmbeddingResponse

logger = logging.getLogger("rag_engine.routes.embeddings")

router = APIRouter(prefix="/api/v1/embeddings", tags=["Embeddings"])


@router.post(
    "/batch",
    response_model=EmbeddingResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate dense vector embeddings for a batch of text segments",
)
async def generate_embeddings_batch(payload: EmbeddingRequest) -> EmbeddingResponse:
    """
    Transforms text chunks into dense float vectors using the active embedding provider.
    """
    if not payload.texts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The texts array must contain at least one item.",
        )

    try:
        provider = get_embedding_provider()
        vectors = await provider.embed_texts(payload.texts)

        items = [
            EmbeddingItem(index=idx, embedding=vec)
            for idx, vec in enumerate(vectors)
        ]

        # Token count estimation
        estimated_tokens = sum(max(1, int(len(t.split()) * 1.3)) for t in payload.texts)

        return EmbeddingResponse(
            model=provider.model_name,
            dimension=provider.dimension,
            total_tokens=estimated_tokens,
            embeddings=items,
        )

    except Exception as exc:
        logger.exception(f"Error during batch embedding generation: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate embeddings: {str(exc)}",
        )
