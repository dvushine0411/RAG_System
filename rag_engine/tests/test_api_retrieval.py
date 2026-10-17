"""
System Role: Automated API integration test validating FastAPI retrieval endpoints.
Inputs: Synthetic JSON requests sent to FastAPI TestClient.
Outputs: Assertion validations confirming HTTP 200, response schema validation, and graceful no_match response.
Ref: ARCHITECTURE.md §2.2 Phase B, §7 Phase 4 Checklist
"""

import os
import sys

import io

# Ensure UTF-8 output on Windows console
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")


# Ensure rag_engine root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from fastapi.testclient import TestClient
from api.main import app
import vectordb.qdrant_client as qc_module
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as rest_models
from config import settings
import asyncio


def run_api_retrieval_tests():
    print("=================================================================")
    print("         PHASE 4 FASTAPI RETRIEVAL ENDPOINT TEST                 ")
    print("=================================================================\n")

    # Provision in-memory Qdrant client for TestClient
    memory_client = AsyncQdrantClient(":memory:")
    asyncio.run(
        memory_client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=rest_models.VectorParams(
                size=settings.embedding_dims,
                distance=rest_models.Distance.COSINE,
            ),
        )
    )
    qc_module.set_qdrant_client(memory_client)

    client = TestClient(app)

    # 1. Test POST /api/v1/retrieval/search with empty DB (should return no_match, not 500)
    print("[TEST 1] Testing POST /api/v1/retrieval/search empty state...")
    payload = {
        "query": "What is HNSW vector indexing?",
        "top_k": 10,
        "ef_search": 40,
        "top_n": 3,
        "rerank": True,
    }
    res = client.post("/api/v1/retrieval/search", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data["query"] == payload["query"]
    assert data["status"] == "no_match"
    assert data["returned_count"] == 0
    assert data["results"] == []
    print("✅ TEST 1 PASSED: Empty search safely returned 200 with status='no_match'.\n")

    # 2. Test POST /retrieve alias endpoint
    print("[TEST 2] Testing POST /retrieve alias endpoint...")
    res_alias = client.post("/retrieve", json=payload)
    assert res_alias.status_code == 200, f"Expected 200, got {res_alias.status_code}: {res_alias.text}"
    data_alias = res_alias.json()
    assert data_alias["status"] == "no_match"
    print("✅ TEST 2 PASSED: /retrieve alias endpoint works identically.\n")

    # 3. Test Invalid payload (empty query string)
    print("[TEST 3] Testing validation rejection for empty query...")
    invalid_res = client.post("/api/v1/retrieval/search", json={"query": ""})
    assert invalid_res.status_code == 422, f"Expected 422 for empty query, got {invalid_res.status_code}"
    print("✅ TEST 3 PASSED: Validation correctly rejected empty query with 422.\n")

    print("=================================================================")
    print("       ALL FASTAPI RETRIEVAL ENDPOINT TESTS PASSED (100%)       ")
    print("=================================================================")


if __name__ == "__main__":
    run_api_retrieval_tests()
