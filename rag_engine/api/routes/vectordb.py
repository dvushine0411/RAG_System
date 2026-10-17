"""
System Role: FastAPI router exposing Vector Database (Qdrant) collection status and vector lifecycle endpoints.
Inputs: Document UUIDs for vector purge and inspection queries.
Outputs: Collection statistics and deletion confirmation DTOs.
Ref: ARCHITECTURE.md §3 & §4.2
"""

import logging
from fastapi import APIRouter, HTTPException, status

from schemas.vectordb import CollectionInfoDTO, VectorDeleteResponse
from vectordb.collection_manager import get_collection_info
from vectordb.vector_ops import delete_vectors_by_document_id

logger = logging.getLogger("rag_engine.routes.vectordb")

router = APIRouter(prefix="/api/v1/vectors", tags=["Vector Database"])


@router.get(
    "/collection/info",
    response_model=CollectionInfoDTO,
    status_code=status.HTTP_200_OK,
    summary="Get collection configuration, HNSW parameters, and point counts",
)
async def get_vector_collection_info() -> CollectionInfoDTO:
    """Returns metadata and HNSW graph parameters for the configured Qdrant collection."""
    try:
        return await get_collection_info()
    except Exception as exc:
        logger.exception(f"Error retrieving collection info: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query collection info: {str(exc)}",
        )


@router.delete(
    "/document/{document_id}",
    response_model=VectorDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Purge all indexed vectors belonging to a specific document",
)
async def delete_document_vectors(document_id: str) -> VectorDeleteResponse:
    """Deletes all chunks indexed in Qdrant matching the provided document_id."""
    if not document_id or not document_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid document_id must be provided.",
        )

    try:
        return await delete_vectors_by_document_id(document_id)
    except Exception as exc:
        logger.exception(f"Error purging vectors for doc {document_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document vectors: {str(exc)}",
        )
