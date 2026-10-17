"""
System Role: Abstract Base Class defining standard interface for Reranker providers.
Inputs: User search query string, list of ScoredChunkDTO vector search candidates, and top_n target count.
Outputs: Re-ordered and re-scored ScoredChunkDTO list.
Ref: ARCHITECTURE.md §2.2 Phase B step 4, §5.1 Technology Decisions
"""

from abc import ABC, abstractmethod
from typing import List
from ingestion.contextual_header import with_header
from schemas.retrieval import ScoredChunkDTO


def rerank_text(chunk: ScoredChunkDTO) -> str:
    """Text scored by the cross-encoder: breadcrumb header (if indexed with one) + chunk content."""
    return with_header((chunk.metadata or {}).get("context_header"), chunk.content)


class BaseRerankerProvider(ABC):
    """
    Abstract interface for cross-encoder rerankers scoring candidate chunks against a query.
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: List[ScoredChunkDTO],
        top_n: int,
    ) -> List[ScoredChunkDTO]:
        """
        Calculates cross-attention / relevance scores for candidate chunks and returns Top-N.

        Args:
            query: User natural language search query.
            chunks: Candidate chunks retrieved by first-stage vector similarity search.
            top_n: Maximum number of top relevant chunks to retain.

        Returns:
            Re-scored and sorted list of ScoredChunkDTO.
        """
        pass
