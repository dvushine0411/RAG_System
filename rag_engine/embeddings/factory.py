"""
System Role: Factory selecting the appropriate embedding provider based on system configuration and API credentials.
Inputs: System configuration settings.
Outputs: An active instance satisfying BaseEmbeddingProvider (OpenAI or Mock fallback).
Ref: ARCHITECTURE.md §5 Centralized Config Principle
"""

import logging
from config import settings
from embeddings.base import BaseEmbeddingProvider
from embeddings.mock_provider import MockEmbeddingProvider

logger = logging.getLogger("rag_engine.embeddings.factory")


_CACHED_PROVIDER: BaseEmbeddingProvider | None = None


def get_embedding_provider() -> BaseEmbeddingProvider:
    """
    Returns a singleton instance of the configured embedding provider.
    Automatically degrades to MockEmbeddingProvider if no OpenAI API Key is configured.
    """
    global _CACHED_PROVIDER
    if _CACHED_PROVIDER is not None:
        return _CACHED_PROVIDER

    if settings.openai_api_key and settings.openai_api_key.strip():
        try:
            from embeddings.openai_provider import OpenAIEmbeddingProvider
            logger.info(f"Initialized OpenAIEmbeddingProvider with model: {settings.embedding_model}")
            _CACHED_PROVIDER = OpenAIEmbeddingProvider()
        except ImportError:
            logger.warning("openai package not installed. Falling back to MockEmbeddingProvider.")
            _CACHED_PROVIDER = MockEmbeddingProvider()
    else:
        logger.warning(
            "OPENAI_API_KEY is unset or empty. Activating deterministic MockEmbeddingProvider for offline testing."
        )
        _CACHED_PROVIDER = MockEmbeddingProvider()

    return _CACHED_PROVIDER

