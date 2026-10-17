"""
System Role: Automated integration test suite validating Phase 4 Retrieval & Reranking pipeline.
Inputs: Synthetic text queries, Qdrant in-memory vector index, and metadata filters.
Outputs: Assertion validations confirming HNSW ef_search parameterization, metadata filtering, reranker scoring, and fallback handling.
Ref: ARCHITECTURE.md §2.2 Phase B, §3.1, §7 Phase 4 Checklist
"""

import asyncio
import os
import io
import sys
import uuid
from typing import List

# Ensure UTF-8 output on Windows console
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure rag_engine root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)



from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as rest_models

from config import settings
from embeddings.mock_provider import MockEmbeddingProvider
from rerankers.base import BaseRerankerProvider
from rerankers.mock_provider import MockRerankerProvider
from schemas.embedding import VectorPointDTO
from schemas.retrieval import (
    RetrievalFilter,
    RetrievalQueryRequest,
    ScoredChunkDTO,
)
import vectordb.qdrant_client as qc_module
from vectordb.vector_ops import search_vectors_with_hnsw, upsert_vectors
from retrieval.retriever import VectorRetriever


class FailingRerankerProvider(BaseRerankerProvider):
    """Simulates a third-party Reranker outage (e.g. Cohere 500 or timeout)."""
    async def rerank(self, query: str, chunks: List[ScoredChunkDTO], top_n: int) -> List[ScoredChunkDTO]:
        raise RuntimeError("Simulated external Cohere Reranker API outage")


async def run_retrieval_test_suite():
    print("=================================================================")
    print("      PHASE 4 RETRIEVAL & RERANKING COMPREHENSIVE TEST SUITE     ")
    print("=================================================================\n")

    # 1. Setup in-memory Qdrant client
    memory_client = AsyncQdrantClient(":memory:")
    collection_name = settings.qdrant_collection

    await memory_client.create_collection(
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

    await memory_client.create_payload_index(
        collection_name=collection_name,
        field_name="document_id",
        field_schema=rest_models.PayloadSchemaType.KEYWORD,
    )

    await memory_client.create_payload_index(
        collection_name=collection_name,
        field_name="source_type",
        field_schema=rest_models.PayloadSchemaType.KEYWORD,
    )

    # Patch global Qdrant client singleton to point to test in-memory instance
    qc_module.set_qdrant_client(memory_client)


    # 2. Seed test documents and chunks
    mock_embedder = MockEmbeddingProvider()
    doc_1_id = str(uuid.uuid4())
    doc_2_id = str(uuid.uuid4())

    corpus = [
        # Document 1 (PDF): Enterprise RAG architecture
        ("Retrieval-Augmented Generation architectures combine dense vector retrieval with LLM generation.", doc_1_id, "pdf", 0, "1. Architecture"),
        ("HNSW Hierarchical Navigable Small World graphs provide logarithmic time complexity search.", doc_1_id, "pdf", 1, "2. Vector Index"),
        ("Cross-Encoder rerankers score candidate chunks with deep all-to-all attention.", doc_1_id, "pdf", 2, "3. Reranker"),
        # Document 2 (Markdown): Microservices & Docker
        ("Docker multi-stage builds optimize production container size for Node.js and FastAPI services.", doc_2_id, "markdown", 0, "Deployment"),
        ("MongoDB stores document metadata and audit logs while Qdrant stores chunk vectors.", doc_2_id, "markdown", 1, "Storage Architecture"),
    ]

    texts = [item[0] for item in corpus]
    vectors = await mock_embedder.embed_texts(texts)

    points: List[VectorPointDTO] = []
    for idx, (content, doc_id, src_type, c_idx, section) in enumerate(corpus):
        p = VectorPointDTO(
            id=str(uuid.uuid4()),
            vector=vectors[idx],
            payload={
                "document_id": doc_id,
                "chunk_index": c_idx,
                "content": content,
                "token_count": len(content.split()) * 2,
                "source_type": src_type,
                "section_title": section,
                "created_at": "2026-10-11T12:00:00Z",
                "department": "Engineering" if src_type == "pdf" else "DevOps",
            },
        )
        points.append(p)

    await upsert_vectors(points)
    print(f"✅ Seeded {len(points)} test chunks across 2 documents into in-memory Qdrant.\n")

    # ──────────────────────────────────────────────────────────
    # TEST 1: Dense HNSW Search with ef_search tuning
    # ──────────────────────────────────────────────────────────
    print("[TEST 1] Testing HNSW Vector Search with efSearch tuning...")
    query_text = "HNSW vector search graphs"
    query_vec = await mock_embedder.embed_query(query_text)


    raw_candidates = await search_vectors_with_hnsw(
        query_vector=query_vec,
        top_k=3,
        ef_search=80,
    )

    assert len(raw_candidates) == 3, f"Expected 3 candidates, got {len(raw_candidates)}"
    scores = [p.score for p in raw_candidates]
    assert all(scores[i] >= scores[i+1] for i in range(len(scores)-1)), "Candidates must be sorted descending by score"
    print(f"  -> Top-1 candidate score: {scores[0]:.4f}")
    p0_payload = raw_candidates[0].payload or {}
    p0_content = str(p0_payload.get("content", ""))
    print(f"  -> Top-1 content preview: '{p0_content[:50]}...'")
    print("✅ TEST 1 PASSED: HNSW search with efSearch executed and ordered correctly.\n")

    # ──────────────────────────────────────────────────────────
    # TEST 2: Metadata Filtering (document_id, source_type, tags)
    # ──────────────────────────────────────────────────────────
    print("[TEST 2] Testing Metadata Filtering...")
    # Filter strictly to doc_2_id (markdown only)
    filtered_results = await search_vectors_with_hnsw(
        query_vector=query_vec,
        top_k=10,
        filter_criteria=RetrievalFilter(
            document_ids=[doc_2_id],
            source_types=["markdown"],
        ),
    )
    assert len(filtered_results) == 2, f"Expected 2 chunks for doc_2_id, got {len(filtered_results)}"
    for r in filtered_results:
        p_load = r.payload or {}
        assert p_load.get("document_id") == doc_2_id, f"Unexpected doc_id: {p_load.get('document_id')}"
        assert p_load.get("source_type") == "markdown", f"Unexpected source_type: {p_load.get('source_type')}"


    # Filter with metadata_match
    dept_results = await search_vectors_with_hnsw(
        query_vector=query_vec,
        top_k=10,
        filter_criteria=RetrievalFilter(
            metadata_match={"department": "DevOps"}
        ),
    )
    assert len(dept_results) == 2, f"Expected 2 chunks with department=DevOps, got {len(dept_results)}"
    print("✅ TEST 2 PASSED: Metadata filters (document_id, source_type, payload match) verified.\n")

    # ──────────────────────────────────────────────────────────
    # TEST 3: VectorRetriever Orchestrator & Two-Stage Reranking
    # ──────────────────────────────────────────────────────────
    print("[TEST 3] Testing VectorRetriever Orchestrator with Mock Reranker...")
    retriever = VectorRetriever()
    retriever.embedding_provider = mock_embedder
    retriever.reranker_provider = MockRerankerProvider()

    req = RetrievalQueryRequest(
        query="Retrieval-Augmented Generation architecture",
        top_k=5,
        top_n=2,
        ef_search=64,
        rerank=True,
    )
    res = await retriever.retrieve_and_rerank(req)

    assert res.status == "success", f"Expected success status, got {res.status}"
    assert res.returned_count == 2, f"Expected top_n=2 returned, got {res.returned_count}"
    assert res.total_candidates >= 2, f"Expected at least 2 candidates, got {res.total_candidates}"
    assert not res.fallback_used, "Fallback should not be used when mock reranker succeeds"
    assert res.results[0].rerank_score is not None, "Rerank score must be populated"
    print(f"  -> Top-1 chunk final score: {res.results[0].final_score}")
    print(f"  -> Top-1 chunk rerank score: {res.results[0].rerank_score}")
    print(f"  -> Top-1 chunk text: '{res.results[0].content[:60]}...'")
    print("✅ TEST 3 PASSED: Two-stage retrieval and reranker scoring succeeded.\n")

    # ──────────────────────────────────────────────────────────
    # TEST 4: Graceful Fallback on Reranker Outage
    # ──────────────────────────────────────────────────────────
    print("[TEST 4] Testing Graceful Fallback when Reranker fails...")
    retriever.reranker_provider = FailingRerankerProvider()

    fallback_res = await retriever.retrieve_and_rerank(req)
    assert fallback_res.status == "success", f"Expected success status, got {fallback_res.status}"
    assert fallback_res.fallback_used is True, "Expected fallback_used=True when reranker throws error"
    assert len(fallback_res.results) == 2, f"Expected 2 results returned, got {len(fallback_res.results)}"
    assert fallback_res.results[0].final_score == fallback_res.results[0].vector_score
    print("  -> Fallback message:", fallback_res.message)
    print("✅ TEST 4 PASSED: Graceful fallback safely activated without crashing.\n")

    # ──────────────────────────────────────────────────────────
    # TEST 5: Empty Retrieval & Cutoff Handling
    # ──────────────────────────────────────────────────
    print("[TEST 5] Testing Empty Retrieval & Min Score Cutoffs...")
    empty_req = RetrievalQueryRequest(
        query="Database schema",
        filter=RetrievalFilter(document_ids=["non-existent-uuid-1234"]),
    )
    empty_res = await retriever.retrieve_and_rerank(empty_req)
    assert empty_res.status == "no_match", f"Expected no_match status, got {empty_res.status}"
    assert empty_res.total_candidates == 0
    assert len(empty_res.results) == 0

    # Score cutoff filter
    high_threshold_req = RetrievalQueryRequest(
        query="Database schema",
        score_threshold=0.9999,  # Impossibly high threshold
    )
    cutoff_res = await retriever.retrieve_and_rerank(high_threshold_req)
    assert cutoff_res.status == "no_match", f"Expected no_match, got {cutoff_res.status}"
    assert len(cutoff_res.results) == 0
    print("✅ TEST 5 PASSED: Empty retrieval and score cutoff filters handled properly.\n")

    print("=================================================================")
    print("   ALL PHASE 4 RETRIEVAL TESTS COMPLETED AND VERIFIED (100%)    ")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(run_retrieval_test_suite())
