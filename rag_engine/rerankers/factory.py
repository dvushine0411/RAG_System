"""
System Role: Factory instantiating Reranker providers based on centralized configuration and environment readiness.
Inputs: Optional provider type override string ('cohere', 'onnx_local', 'mock').
Outputs: Concrete instance of BaseRerankerProvider.
Ref: ARCHITECTURE.md §5.1, §5.2 Directory Dictionary
"""

import logging
from typing import Dict, Optional, Tuple

from config import settings
from rerankers.base import BaseRerankerProvider
from rerankers.mock_provider import MockRerankerProvider
from rerankers.cohere_provider import CohereRerankerProvider
from rerankers.onnx_provider import LocalONNXRerankerProvider

logger = logging.getLogger("rag_engine.rerankers.factory")


# Reuse provider instances (and their HTTP clients) across queries.
_PROVIDER_CACHE: Dict[Tuple[str, str, bool], BaseRerankerProvider] = {}


def get_reranker_provider(provider_type: Optional[str] = None) -> BaseRerankerProvider:
    """Cached provider per (type, model, credentials present)."""
    selected = (provider_type or settings.reranker_provider).lower()
    key = (selected, settings.reranker_model, bool(settings.cohere_api_key))
    if key not in _PROVIDER_CACHE:
        _PROVIDER_CACHE[key] = _build_reranker_provider(selected)
    return _PROVIDER_CACHE[key]


def _build_reranker_provider(provider_type: Optional[str] = None) -> BaseRerankerProvider:
    """
    Factory function resolving and returning the appropriate BaseRerankerProvider.

    Resolution logic:
    1. If provider_type is explicitly given, prioritize it.
    2. Otherwise, read settings.reranker_provider.
    3. If 'cohere' is selected but COHERE_API_KEY is not configured, gracefully fall back to MockRerankerProvider.
    4. If 'onnx_local' is selected, instantiate LocalONNXRerankerProvider.
    5. If 'mock' is selected, instantiate MockRerankerProvider.
    """
    selected_type = (provider_type or settings.reranker_provider).lower()

    if selected_type == "cohere":
        if settings.cohere_api_key:
            return CohereRerankerProvider(api_key=settings.cohere_api_key, model=settings.reranker_model)
        logger.warning(
            "COHERE_API_KEY is empty. Falling back to MockRerankerProvider for offline execution."
        )
        return MockRerankerProvider()

    if selected_type in ("onnx", "onnx_local"):
        return LocalONNXRerankerProvider()

    if selected_type == "mock":
        return MockRerankerProvider()

    logger.warning(f"Unknown reranker provider '{selected_type}'. Defaulting to MockRerankerProvider.")
    return MockRerankerProvider()
