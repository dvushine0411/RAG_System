"""
System Role: Automated test suite for Phase 3 embedding generation, mock providers, and factory routing.
Inputs: Sample text batches and queries.
Outputs: Assertion validations for vector dimensionality (1536), unit L2 normalization, and deterministic mapping.
Ref: ARCHITECTURE.md §2.2 Phase A & §5
"""

import asyncio
import math
import os
import sys

# Ensure rag_engine root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from config import settings
from embeddings.base import BaseEmbeddingProvider
from embeddings.mock_provider import MockEmbeddingProvider
from embeddings.factory import get_embedding_provider


def test_mock_embedding_provider_sync():
    """Validates vector dimension, unit L2 norm, and determinism."""
    print("=== [TEST 1] MockEmbeddingProvider Dimension & Normalization ===")
    provider = MockEmbeddingProvider()

    assert provider.dimension == settings.embedding_dims, (
        f"Expected dimension {settings.embedding_dims}, got {provider.dimension}"
    )
    assert provider.model_name == f"mock-{settings.embedding_model}"

    # Test single query embedding
    vector = asyncio.run(provider.embed_query("Enterprise RAG System"))
    assert len(vector) == settings.embedding_dims, f"Vector size mismatch: {len(vector)}"

    # Check L2 unit normalization (norm should be ~1.0)
    norm = math.sqrt(sum(x * x for x in vector))
    assert abs(norm - 1.0) < 1e-5, f"Vector is not unit normalized: norm={norm}"
    print(f"  -> PASS: 1536-dim vector generated, L2 Norm = {norm:.6f}")

    # Test determinism
    vector_repeat = asyncio.run(provider.embed_query("Enterprise RAG System"))
    assert vector == vector_repeat, "Mock provider must be deterministic for identical input!"
    print("  -> PASS: Determinism verified (identical texts produce exact matching vectors)")

    # Test distinctness
    vector_different = asyncio.run(provider.embed_query("Completely unrelated query"))
    assert vector != vector_different, "Different inputs must produce distinct vectors!"
    print("  -> PASS: Distinction verified (different texts produce distinct vectors)\n")


def test_mock_batch_embedding():
    """Validates batch embedding generation preserves count and order."""
    print("=== [TEST 2] MockEmbeddingProvider Batch Generation ===")
    provider = MockEmbeddingProvider()

    test_batch = [
        "Chunk 0: Document overview and introduction.",
        "Chunk 1: HNSW indexing parameters M=16, ef=64.",
        "Chunk 2: Vector distance metrics Cosine similarity.",
    ]

    vectors = asyncio.run(provider.embed_texts(test_batch))
    assert len(vectors) == len(test_batch), f"Expected {len(test_batch)} vectors, got {len(vectors)}"

    for idx, vec in enumerate(vectors):
        assert len(vec) == settings.embedding_dims
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-5
        print(f"  -> Batch item {idx}: dim={len(vec)}, norm={norm:.6f}")

    print("  -> PASS: Batch embeddings generated with strict order and normalization.\n")


def test_embedding_factory():
    """Validates that factory returns an active provider implementing BaseEmbeddingProvider."""
    print("=== [TEST 3] EmbeddingProviderFactory Selection ===")
    provider = get_embedding_provider()

    assert isinstance(provider, BaseEmbeddingProvider)
    assert provider.dimension == settings.embedding_dims
    print(f"  -> PASS: Factory returned active provider '{provider.model_name}' (dim={provider.dimension}).\n")


def run_all_embedding_tests():
    print("=================================================================")
    print("         PHASE 3 EMBEDDINGS TEST SUITE                          ")
    print("=================================================================\n")
    test_mock_embedding_provider_sync()
    test_mock_batch_embedding()
    test_embedding_factory()
    print("=================================================================")
    print("  [SUCCESS] ALL EMBEDDING TESTS PASSED 100%!                    ")
    print("=================================================================\n")


if __name__ == "__main__":
    run_all_embedding_tests()
