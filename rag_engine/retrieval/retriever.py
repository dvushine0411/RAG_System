"""
System Role: Core Retrieval & Reranking orchestration engine executing dense HNSW search, metadata filtering, and two-stage cross-encoder reranking.
Inputs: RetrievalQueryRequest with natural language query, metadata filters, and HNSW hyperparameters.
Outputs: RetrievalResponse containing ranked ScoredChunkDTO candidates with vector and rerank scores.
Ref: ARCHITECTURE.md §2.2 Phase B, §3.1, §5.1, §5.2 Centralized Config Principle
"""

import logging
from typing import List, Optional

from config import settings
from embeddings.factory import get_embedding_provider
from rerankers.factory import get_reranker_provider
from schemas.retrieval import (
    RetrievalQueryRequest,
    RetrievalResponse,
    ScoredChunkDTO,
)
from vectordb.vector_ops import search_vectors_with_hnsw

logger = logging.getLogger("rag_engine.retrieval.retriever")


class VectorRetriever:
    """
    Coordinates dense vector retrieval and cross-encoder reranking with graceful fallbacks.
    """

    def __init__(self):
        self.embedding_provider = get_embedding_provider()
        self.reranker_provider = get_reranker_provider()

    async def retrieve_and_rerank(
        self,
        request: RetrievalQueryRequest,
    ) -> RetrievalResponse:
        """
        Executes end-to-end retrieval:
        1. Embed user query into 1536-dim vector space.
        2. Perform approximate nearest neighbor (ANN) search on Qdrant HNSW index with filters.
        3. Convert matches to ScoredChunkDTO candidates.
        4. Apply cross-encoder reranking if requested; fallback to vector scores on failure.
        5. Apply score threshold filtering and assemble response.
        """
        query_text = request.query.strip()
        if not query_text:
            return RetrievalResponse(
                query=request.query,
                total_candidates=0,
                returned_count=0,
                fallback_used=False,
                status="no_match",
                message="Query string cannot be empty.",
                results=[],
            )

        # 1. Generate query embedding
        logger.info(f"Generating query embedding for: '{query_text[:60]}...'")
        query_vector = await self.embedding_provider.embed_query(query_text)


        # 2. HNSW Vector Similarity Search
        top_k = request.top_k if request.top_k is not None else settings.retrieval_top_k
        ef_search = request.ef_search if request.ef_search is not None else settings.hnsw_ef_search
        top_n = request.top_n if request.top_n is not None else settings.rerank_top_n

        raw_points = await search_vectors_with_hnsw(
            query_vector=query_vector,
            top_k=top_k,
            ef_search=ef_search,
            filter_criteria=request.filter,
            score_threshold=request.score_threshold,
        )

        total_candidates = len(raw_points)
        if total_candidates == 0:
            logger.info("No matching chunks found in Qdrant vector index for given query and filters.")
            return RetrievalResponse(
                query=query_text,
                total_candidates=0,
                returned_count=0,
                fallback_used=False,
                status="no_match",
                message="No matching chunks found in vector database.",
                results=[],
            )

        # 3. Assemble candidate DTOs
        candidate_dtos: List[ScoredChunkDTO] = []
        for point in raw_points:
            payload = point.payload or {}
            vector_score = round(float(point.score), 4)

            # Extract reserved payload fields
            document_id = str(payload.get("document_id", ""))
            chunk_index = int(payload.get("chunk_index", 0))
            content = str(payload.get("content", ""))
            token_count = int(payload.get("token_count", 0))
            source_type = str(payload.get("source_type", "unknown"))
            page_number = payload.get("page_number")
            section_title = payload.get("section_title")

            # Collect non-reserved payload fields into metadata dict
            reserved_keys = {
                "document_id", "chunk_index", "content", "token_count",
                "source_type", "page_number", "section_title", "created_at"
            }
            extra_metadata = {k: v for k, v in payload.items() if k not in reserved_keys}

            dto = ScoredChunkDTO(
                id=str(point.id),
                document_id=document_id,
                chunk_index=chunk_index,
                content=content,
                token_count=token_count,
                source_type=source_type,
                page_number=page_number,
                section_title=section_title,
                vector_score=vector_score,
                rerank_score=None,
                final_score=vector_score,
                metadata=extra_metadata,
            )
            candidate_dtos.append(dto)

        # 4. Two-Stage Reranking with Graceful Fallback
        fallback_used = False
        reranked_chunks: List[ScoredChunkDTO] = []

        if request.rerank:
            try:
                logger.info(f"Executing cross-encoder reranking on {len(candidate_dtos)} candidate chunks...")
                reranked_chunks = await self.reranker_provider.rerank(
                    query=query_text,
                    chunks=candidate_dtos,
                    top_n=top_n,
                )
            except Exception as rerank_err:
                logger.warning(
                    f"Reranker service failed with error: '{rerank_err}'. "
                    "Gracefully activating fallback: sorting by vector similarity score."
                )
                fallback_used = True
                sorted_by_vector = sorted(candidate_dtos, key=lambda c: c.vector_score, reverse=True)
                reranked_chunks = [
                    c.model_copy(update={"final_score": c.vector_score})
                    for c in sorted_by_vector[:top_n]
                ]
        else:
            sorted_by_vector = sorted(candidate_dtos, key=lambda c: c.vector_score, reverse=True)
            reranked_chunks = [
                c.model_copy(update={"final_score": c.vector_score})
                for c in sorted_by_vector[:top_n]
            ]

        # 5. Score threshold cutoff on final results
        if request.rerank_min_score is not None:
            min_cutoff = request.rerank_min_score
        elif request.score_threshold is not None:
            min_cutoff = request.score_threshold
        else:
            min_cutoff = settings.rerank_min_score
        final_results: List[ScoredChunkDTO] = []
        for chunk in reranked_chunks:
            if min_cutoff > 0.0 and chunk.final_score < min_cutoff:
                continue
            final_results.append(chunk)

        if not final_results:
            return RetrievalResponse(
                query=query_text,
                total_candidates=total_candidates,
                returned_count=0,
                fallback_used=fallback_used,
                status="no_match",
                message="Candidates found but none exceeded the minimum confidence score threshold.",
                results=[],
            )

        return RetrievalResponse(
            query=query_text,
            total_candidates=total_candidates,
            returned_count=len(final_results),
            fallback_used=fallback_used,
            status="success",
            message="Retrieval and reranking completed successfully." if not fallback_used else "Completed with vector ranking fallback.",
            results=final_results,
        )
