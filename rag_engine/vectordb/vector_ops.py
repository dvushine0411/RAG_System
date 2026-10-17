"""
System Role: Vector Database operations module executing point upserts, HNSW similarity searches with metadata filtering, and document deletions.
Inputs: VectorPointDTO lists for indexing, document UUIDs for purging, or dense query vectors with RetrievalFilter.
Outputs: Execution confirmation DTOs or lists of ScoredPoint objects from Qdrant.
Ref: ARCHITECTURE.md §3, §4.2, §5.2 Centralized Config Principle
"""

import logging
from typing import List, Optional, Any
from qdrant_client.http import models as rest_models

from config import settings
from schemas.embedding import VectorPointDTO
from schemas.retrieval import RetrievalFilter
from schemas.vectordb import VectorDeleteResponse, VectorUpsertResponse
from vectordb.qdrant_client import get_qdrant_client

logger = logging.getLogger("rag_engine.vectordb.ops")


def build_qdrant_filter(filter_criteria: Optional[RetrievalFilter]) -> Optional[rest_models.Filter]:
    """
    Constructs a Qdrant Filter from RetrievalFilter constraints.

    Args:
        filter_criteria: Optional filtering rules (document_ids, source_types, dates, metadata_match).

    Returns:
        rest_models.Filter or None if no filter conditions are provided.
    """
    if not filter_criteria:
        return None

    must_conditions: List[rest_models.Condition] = []

    # Filter by document_ids
    if filter_criteria.document_ids:
        if len(filter_criteria.document_ids) == 1:
            must_conditions.append(
                rest_models.FieldCondition(
                    key="document_id",
                    match=rest_models.MatchValue(value=filter_criteria.document_ids[0])
                )
            )
        else:
            must_conditions.append(
                rest_models.FieldCondition(
                    key="document_id",
                    match=rest_models.MatchAny(any=filter_criteria.document_ids)
                )
            )

    # Filter by source_types
    if filter_criteria.source_types:
        if len(filter_criteria.source_types) == 1:
            must_conditions.append(
                rest_models.FieldCondition(
                    key="source_type",
                    match=rest_models.MatchValue(value=filter_criteria.source_types[0])
                )
            )
        else:
            must_conditions.append(
                rest_models.FieldCondition(
                    key="source_type",
                    match=rest_models.MatchAny(any=filter_criteria.source_types)
                )
            )

    # Filter by created_at range
    if filter_criteria.created_after or filter_criteria.created_before:
        range_kwargs = {}
        if filter_criteria.created_after:
            range_kwargs["gte"] = filter_criteria.created_after
        if filter_criteria.created_before:
            range_kwargs["lte"] = filter_criteria.created_before
        must_conditions.append(
            rest_models.FieldCondition(
                key="created_at",
                range=rest_models.DatetimeRange(**range_kwargs)
            )
        )

    # Filter by arbitrary payload metadata match
    if filter_criteria.metadata_match:
        for field_key, field_value in filter_criteria.metadata_match.items():
            must_conditions.append(
                rest_models.FieldCondition(
                    key=field_key,
                    match=rest_models.MatchValue(value=field_value)
                )
            )

    if not must_conditions:
        return None

    return rest_models.Filter(must=must_conditions)



async def search_vectors_with_hnsw(
    query_vector: List[float],
    top_k: Optional[int] = None,
    ef_search: Optional[int] = None,
    filter_criteria: Optional[RetrievalFilter] = None,
    score_threshold: Optional[float] = None,
) -> List[rest_models.ScoredPoint]:
    """
    Executes approximate nearest neighbor (ANN) vector search on Qdrant HNSW index.

    Args:
        query_vector: 1536-dimensional normalized query embedding.
        top_k: Number of candidate chunks to return (defaults to settings.retrieval_top_k).
        ef_search: Query-time exploration depth efSearch (defaults to settings.hnsw_ef_search).
        filter_criteria: Optional metadata filters.
        score_threshold: Minimum cosine similarity score threshold.

    Returns:
        List of Qdrant ScoredPoint objects ordered by similarity descending.
    """
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection
    limit = top_k if top_k is not None else settings.retrieval_top_k
    ef = ef_search if ef_search is not None else settings.hnsw_ef_search
    min_score = score_threshold if score_threshold is not None else settings.retrieval_min_score

    query_filter = build_qdrant_filter(filter_criteria)
    search_params = rest_models.SearchParams(hnsw_ef=ef)

    score_thresh: Optional[float] = min_score if min_score > 0.0 else None

    results = await client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=limit,
        search_params=search_params,
        query_filter=query_filter,
        score_threshold=score_thresh,
    )
    logger.info(
        f"HNSW search in '{collection_name}' returned {len(results)} chunks "
        f"(limit={limit}, ef_search={ef}, filtered={query_filter is not None})."
    )
    return results


async def upsert_vectors(points: List[VectorPointDTO]) -> VectorUpsertResponse:
    """
    Upserts a batch of vectorized points with content and metadata payloads into Qdrant.

    Args:
        points: List of VectorPointDTO containing point IDs, 1536-dim vectors, and chunk payloads.

    Returns:
        VectorUpsertResponse with stored count and status.
    """
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection

    qdrant_points = [
        rest_models.PointStruct(
            id=p.id,
            vector=p.vector,
            payload=p.payload,
        )
        for p in points
    ]

    await client.upsert(
        collection_name=collection_name,
        points=qdrant_points,
        wait=True,
    )

    logger.info(f"Upserted {len(qdrant_points)} points into Qdrant collection '{collection_name}'.")
    return VectorUpsertResponse(
        collection_name=collection_name,
        upserted_count=len(qdrant_points),
        status="completed",
    )


async def delete_vectors_by_document_id(document_id: str) -> VectorDeleteResponse:
    """
    Deletes all vector points associated with a specific document_id filter from Qdrant.

    Args:
        document_id: Document UUID whose chunks should be expunged.

    Returns:
        VectorDeleteResponse confirming deletion.
    """
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection

    await client.delete(
        collection_name=collection_name,
        points_selector=rest_models.FilterSelector(
            filter=rest_models.Filter(
                must=[
                    rest_models.FieldCondition(
                        key="document_id",
                        match=rest_models.MatchValue(value=document_id),
                    )
                ]
            )
        ),
        wait=True,
    )

    logger.info(f"Purged all vector points for document_id='{document_id}' from '{collection_name}'.")
    return VectorDeleteResponse(
        collection_name=collection_name,
        document_id=document_id,
        status="completed",
    )


async def count_collection_vectors() -> int:
    """Returns the total number of indexed points in the active collection."""
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection
    count_result = await client.count(collection_name=collection_name, exact=True)
    return count_result.count

