"""
System Role: Production Reranker provider client communicating with Cohere Rerank API.
Inputs: User search query, candidate ScoredChunkDTO list, and target top_n limit.
Outputs: ScoredChunkDTO list re-ordered and annotated with cross-attention relevance scores.
Ref: ARCHITECTURE.md §2.2 Phase B step 4, §5.1 Centralized Config Principle
"""

import logging
from typing import Any, List
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from schemas.retrieval import ScoredChunkDTO
from rerankers.base import rerank_text, BaseRerankerProvider

logger = logging.getLogger("rag_engine.rerankers.cohere")


class CohereRerankerProvider(BaseRerankerProvider):
    """
    Production Reranker provider using Cohere Rerank v3 API with retry backoff.
    """

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or settings.cohere_api_key
        if not self.api_key:
            raise ValueError(
                "Cohere API key is not configured. Set COHERE_API_KEY or use Mock/Local reranker provider."
            )
        self.model = model or settings.reranker_model
        self._client: Any = None  # created once, reused (keep-alive) across rerank calls

    def warm_up(self) -> None:
        """Import the (slow, ~5 s) Cohere SDK and build the client ahead of the first request."""
        if self._client is None:
            import cohere  # type: ignore

            self._client = cohere.AsyncClient(api_key=self.api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _call_rerank_api(
        self,
        client: Any,
        query: str,
        documents: List[str],
        top_n: int,
    ) -> Any:
        """Invokes Cohere Rerank API with tenacity exponential retry."""
        return await client.rerank(
            model=self.model,
            query=query,
            documents=documents,
            top_n=top_n,
        )

    async def rerank(
        self,
        query: str,
        chunks: List[ScoredChunkDTO],
        top_n: int,
    ) -> List[ScoredChunkDTO]:
        if not chunks:
            return []

        # Lazy import cohere SDK to avoid module error in environments without cohere
        try:
            import cohere  # type: ignore
        except ImportError as exc:
            raise ImportError("Cohere SDK not installed. Run pip install cohere==5.11.0.") from exc

        if self._client is None:
            self._client = cohere.AsyncClient(api_key=self.api_key)
        client: Any = self._client

        documents = [rerank_text(c) for c in chunks]

        logger.info(
            f"Sending {len(documents)} chunks to Cohere Rerank API (model='{self.model}', top_n={top_n})."
        )

        response = await self._call_rerank_api(
            client=client,
            query=query,
            documents=documents,
            top_n=top_n,
        )

        scored_results: List[ScoredChunkDTO] = []
        for result in response.results:
            original_chunk = chunks[result.index]
            relevance = float(result.relevance_score)
            scored_chunk = original_chunk.model_copy(
                update={
                    "rerank_score": relevance,
                    "final_score": relevance,
                }
            )
            scored_results.append(scored_chunk)

        # Sort descending by rerank score
        scored_results.sort(key=lambda c: c.final_score, reverse=True)
        return scored_results
