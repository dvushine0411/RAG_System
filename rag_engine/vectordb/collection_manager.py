"""
System Role: Collection lifecycle manager ensuring Qdrant collections and HNSW indices adhere to architecture parameters.
Inputs: Qdrant client connection and centralized schema settings.
Outputs: Initialized vector collections with optimized HNSW graphs and payload keyword indices.
Ref: ARCHITECTURE.md §3 & §4.2 Centralized Config Principle
"""

import logging
from qdrant_client.http import models as rest_models
from qdrant_client.http.exceptions import UnexpectedResponse

from config import settings
from schemas.vectordb import CollectionInfoDTO
from vectordb.qdrant_client import get_qdrant_client

logger = logging.getLogger("rag_engine.vectordb.collection_manager")


async def ensure_collection_exists() -> bool:
    """
    Verifies that the target Qdrant collection exists.
    If absent, provisions it with strict HNSW indexing parameters and a keyword index on document_id.
    """
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection

    try:
        collections_response = await client.get_collections()
        existing_names = [col.name for col in collections_response.collections]

        if collection_name in existing_names:
            logger.info(f"Qdrant collection '{collection_name}' already exists.")
            return True

        logger.info(
            f"Creating Qdrant collection '{collection_name}' "
            f"(dim={settings.embedding_dims}, metric=Cosine, HNSW M={settings.hnsw_m}, ef_construct={settings.hnsw_ef_construction})..."
        )

        try:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=rest_models.VectorParams(
                    size=settings.embedding_dims,
                    distance=rest_models.Distance.COSINE,
                ),
                hnsw_config=rest_models.HnswConfigDiff(
                    m=settings.hnsw_m,
                    ef_construct=settings.hnsw_ef_construction,
                ),
            )
        except UnexpectedResponse as exc:
            # Multiple uvicorn workers race at startup: another worker created it first.
            if exc.status_code != 409:
                raise
            logger.info(f"Qdrant collection '{collection_name}' was created concurrently by another worker.")

        # Create payload index for document_id to optimize filtering and deletion
        await client.create_payload_index(
            collection_name=collection_name,
            field_name="document_id",
            field_schema=rest_models.PayloadSchemaType.KEYWORD,
        )

        logger.info(f"Successfully provisioned collection '{collection_name}' with payload keyword index.")
        return True

    except Exception as exc:
        logger.error(f"Failed to verify/create Qdrant collection '{collection_name}': {exc}")
        raise exc


async def get_collection_info() -> CollectionInfoDTO:
    """Retrieves operational statistics and HNSW parameters for the active collection."""
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection

    info = await client.get_collection(collection_name=collection_name)
    vectors_count = info.points_count or 0

    return CollectionInfoDTO(
        name=collection_name,
        status=str(info.status.value if hasattr(info.status, "value") else info.status),
        vectors_count=vectors_count,
        dimension=settings.embedding_dims,
        distance="Cosine",
        hnsw_m=settings.hnsw_m,
        hnsw_ef_construct=settings.hnsw_ef_construction,
    )
