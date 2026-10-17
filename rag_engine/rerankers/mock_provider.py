"""
System Role: Deterministic offline mock reranker provider for test execution and CI without API keys.
Inputs: User search query, candidate ScoredChunkDTO list, and target top_n count.
Outputs: Deterministically re-scored and ranked ScoredChunkDTO list.
Ref: ARCHITECTURE.md §5.2 Directory Dictionary
"""

import logging
from typing import List
from schemas.retrieval import ScoredChunkDTO
from rerankers.base import rerank_text, BaseRerankerProvider

logger = logging.getLogger("rag_engine.rerankers.mock")


class MockRerankerProvider(BaseRerankerProvider):
    """
    Offline deterministic mock reranker calculating token overlap & bounded scores for CI/CD testing.
    """

    async def rerank(
        self,
        query: str,
        chunks: List[ScoredChunkDTO],
        top_n: int,
    ) -> List[ScoredChunkDTO]:
        if not chunks:
            return []

        query_tokens = set(query.lower().split())
        scored_results: List[ScoredChunkDTO] = []

        for chunk in chunks:
            content_tokens = set(rerank_text(chunk).lower().split())
            overlap = len(query_tokens.intersection(content_tokens))

            # Calibrate mock score: combine token overlap with original vector score, bounded in [0.0, 1.0]
            overlap_score = min(overlap / max(len(query_tokens), 1), 1.0)
            mock_score = round(0.5 * chunk.vector_score + 0.5 * overlap_score, 4)

            scored_chunk = chunk.model_copy(
                update={
                    "rerank_score": mock_score,
                    "final_score": mock_score,
                }
            )
            scored_results.append(scored_chunk)

        # Sort descending by final_score
        scored_results.sort(key=lambda c: c.final_score, reverse=True)
        top_candidates = scored_results[:top_n]

        logger.info(
            f"MockReranker processed {len(chunks)} candidate chunks -> returned top {len(top_candidates)} (top_n={top_n})."
        )
        return top_candidates
