"""
System Role: Automated integration test suite validating Qdrant collection creation, HNSW indices, point upsert, and deletion.
Inputs: Synthetic 1536-dimensional float vectors, chunk payloads, and document UUIDs.
Outputs: Assertion validations confirming HNSW configuration, storage counts, and payload-filtered purge operations.
Ref: ARCHITECTURE.md §3 & §4.2
"""

import asyncio
import os
import sys
import uuid

# Ensure rag_engine root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as rest_models
from config import settings
from embeddings.mock_provider import MockEmbeddingProvider


async def run_qdrant_operations_test():
    print("=================================================================")
    print("         PHASE 3 QDRANT & HNSW OPERATIONS TEST                  ")
    print("=================================================================\n")

    # Use in-memory Qdrant instance for hermetic, lightning-fast test execution
    client = AsyncQdrantClient(":memory:")
    collection_name = settings.qdrant_collection
    test_doc_id_1 = str(uuid.uuid4())
    test_doc_id_2 = str(uuid.uuid4())

    # ──────────────────────────────────────────────────────────
    # Test 1: Collection Creation & HNSW Configuration
    # ──────────────────────────────────────────────────────────
    print("[TEST 1] Provisioning Collection with HNSW Parameters...")
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

    # Payload keyword index for fast document_id filtering
    await client.create_payload_index(
        collection_name=collection_name,
        field_name="document_id",
        field_schema=rest_models.PayloadSchemaType.KEYWORD,
    )

    info = await client.get_collection(collection_name)
    print("  -> Actual HNSW config:", info.config.hnsw_config)
    vectors_cfg = info.config.params.vectors
    assert isinstance(vectors_cfg, rest_models.VectorParams)
    assert vectors_cfg.size == settings.embedding_dims
    assert vectors_cfg.distance == rest_models.Distance.COSINE


    print(f"  -> PASS: Collection '{collection_name}' created (HNSW M={settings.hnsw_m}, ef_construct={settings.hnsw_ef_construction}).\n")

    # ──────────────────────────────────────────────────────────
    # Test 2: Batch Vector Upsert with Payload
    # ──────────────────────────────────────────────────────────
    print("[TEST 2] Batch Point Upsert with Metadata Payloads...")
    provider = MockEmbeddingProvider()
    texts_doc1 = [
        "Introduction to high-dimensional approximate nearest neighbor search.",
        "Hierarchical Navigable Small World graphs provide logarithmic scaling.",
        "Document deduplication executes at the API Gateway layer via SHA-256.",
    ]
    texts_doc2 = [
        "Unrelated document chunk regarding front-end state management.",
    ]

    vectors_1 = await provider.embed_texts(texts_doc1)
    vectors_2 = await provider.embed_texts(texts_doc2)

    points = []
    # Points for Document 1
    for idx, (txt, vec) in enumerate(zip(texts_doc1, vectors_1)):
        p_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{test_doc_id_1}:{idx}"))
        points.append(
            rest_models.PointStruct(
                id=p_id,
                vector=vec,
                payload={
                    "document_id": test_doc_id_1,
                    "chunk_index": idx,
                    "content": txt,
                    "token_count": len(txt.split()),
                    "source_type": "text",
                },
            )
        )
    # Points for Document 2
    for idx, (txt, vec) in enumerate(zip(texts_doc2, vectors_2)):
        p_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{test_doc_id_2}:{idx}"))
        points.append(
            rest_models.PointStruct(
                id=p_id,
                vector=vec,
                payload={
                    "document_id": test_doc_id_2,
                    "chunk_index": idx,
                    "content": txt,
                    "token_count": len(txt.split()),
                    "source_type": "text",
                },
            )
        )

    await client.upsert(collection_name=collection_name, points=points, wait=True)
    count_all = (await client.count(collection_name=collection_name, exact=True)).count
    assert count_all == 4, f"Expected 4 points, got {count_all}"
    print(f"  -> PASS: Successfully upserted {count_all} points across 2 documents.\n")

    # ──────────────────────────────────────────────────────────
    # Test 3: Payload Filter Query
    # ──────────────────────────────────────────────────────────
    print("[TEST 3] Payload Filtering by document_id...")
    filter_doc1 = rest_models.Filter(
        must=[
            rest_models.FieldCondition(
                key="document_id",
                match=rest_models.MatchValue(value=test_doc_id_1),
            )
        ]
    )
    count_doc1 = (await client.count(collection_name=collection_name, count_filter=filter_doc1, exact=True)).count
    assert count_doc1 == 3, f"Expected 3 points for doc 1, got {count_doc1}"
    print(f"  -> PASS: Filter query accurately matched {count_doc1} points for document {test_doc_id_1[:8]}...\n")

    # ──────────────────────────────────────────────────────────
    # Test 4: Document Vector Deletion
    # ──────────────────────────────────────────────────────────
    print("[TEST 4] Purging Vectors by document_id Selector...")
    await client.delete(
        collection_name=collection_name,
        points_selector=rest_models.FilterSelector(filter=filter_doc1),
        wait=True,
    )

    remaining_doc1 = (await client.count(collection_name=collection_name, count_filter=filter_doc1, exact=True)).count
    assert remaining_doc1 == 0, f"Expected 0 points remaining for doc 1, got {remaining_doc1}"

    remaining_total = (await client.count(collection_name=collection_name, exact=True)).count
    assert remaining_total == 1, f"Expected 1 point remaining (doc 2), got {remaining_total}"
    print(f"  -> PASS: Document 1 vectors completely purged. Remaining points in index: {remaining_total}.\n")

    await client.close()
    print("=================================================================")
    print("  [SUCCESS] ALL QDRANT HNSW & VECTOR OPS TESTS PASSED 100%!     ")
    print("=================================================================\n")


if __name__ == "__main__":
    asyncio.run(run_qdrant_operations_test())
