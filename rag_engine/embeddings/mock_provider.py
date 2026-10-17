"""
System Role: Deterministic mock vector embedding provider for offline testing and development environments.
Inputs: Lists of text strings or query strings.
Outputs: Deterministic, unit-normalized 1536-dimensional float vectors matching the production model size.
Ref: ARCHITECTURE.md §5 Centralized Config Principle
"""

import hashlib
import math
from typing import List

from config import settings
from embeddings.base import BaseEmbeddingProvider


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Generates reproducible unit-normalized vectors without external API calls."""

    def __init__(self) -> None:
        self._dimension = settings.embedding_dims
        self._model_name = f"mock-{settings.embedding_model}"

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def _generate_vector(self, text: str) -> List[float]:
        """Creates a deterministic unit-normalized vector seeded by text content."""
        hasher = hashlib.sha256(text.encode("utf-8"))
        seed_bytes = hasher.digest()

        raw_vector: List[float] = []
        for i in range(self._dimension):
            byte_val = seed_bytes[i % len(seed_bytes)]
            val = ((byte_val + i) % 100) / 100.0 - 0.5
            raw_vector.append(val)

        # Normalize to unit length (L2 norm) for cosine distance
        norm = math.sqrt(sum(x * x for x in raw_vector))
        if norm == 0.0:
            return [0.0] * self._dimension
        return [x / norm for x in raw_vector]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Vectorizes a batch of texts synchronously wrapped in coroutine."""
        return [self._generate_vector(t) for t in texts]

    async def embed_query(self, text: str) -> List[float]:
        """Vectorizes a query string synchronously wrapped in coroutine."""
        return self._generate_vector(text)
