"""
System Role: Production embedding provider utilizing OpenAI API (text-embedding-3-small) with batching and retry logic.
Inputs: Text chunk batches or query strings.
Outputs: 1536-dimensional dense float vector embeddings.
Ref: ARCHITECTURE.md §2.2 & §5 Centralized Config Principle
"""

import logging
from typing import List
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings
from embeddings.base import BaseEmbeddingProvider

logger = logging.getLogger("rag_engine.embeddings.openai")


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Generates dense vector embeddings via OpenAI API with tenacity retry backoff."""

    def __init__(self) -> None:
        self._model = settings.embedding_model
        self._dimension = settings.embedding_dims
        self._batch_size = settings.embedding_batch_size
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model

    @retry(
        stop=stop_after_attempt(settings.embedding_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _embed_batch_with_retry(self, batch: List[str]) -> List[List[float]]:
        """Invokes OpenAI embedding endpoint for a single batch with exponential retry."""
        response = await self._client.embeddings.create(
            model=self._model,
            input=batch,
            dimensions=self._dimension,
        )
        # Sort by index to maintain ordering guarantees
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Chunks texts into batches matching settings.embedding_batch_size
        and vectorizes them sequentially with error isolation.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            batch_vectors = await self._embed_batch_with_retry(batch)
            all_embeddings.extend(batch_vectors)

        return all_embeddings

    async def embed_query(self, text: str) -> List[float]:
        """Embeds an isolated query string for vector search."""
        vectors = await self._embed_batch_with_retry([text])
        return vectors[0]
