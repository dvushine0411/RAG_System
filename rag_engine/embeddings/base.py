"""
System Role: Abstract Base Class defining the contract for all vector embedding providers.
Inputs: Lists of text strings (batch) or individual query strings.
Outputs: Dense float vectors matching the configured embedding dimension.
Ref: ARCHITECTURE.md §2.2 Phase A & §5
"""

from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingProvider(ABC):
    """Abstract interface for text embedding generation."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Returns the dimensionality of the generated vectors."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Returns the identifier name of the underlying embedding model."""
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generates dense vector embeddings for a batch of text segments.

        Args:
            texts: List of string chunks to vectorize.

        Returns:
            List of float vector arrays.
        """
        pass

    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """
        Generates a dense vector embedding for a single search query.

        Args:
            text: Query string.

        Returns:
            Single float vector array.
        """
        pass
