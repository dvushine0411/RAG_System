"""
System Role: LLM Provider Factory resolving OpenAI, Gemini, Anthropic, or Mock provider with graceful fallback.
Inputs: Provider name and model configuration strings from settings or request overrides.
Outputs: Initialized BaseLLMProvider instance ready for asynchronous streaming.
Ref: ARCHITECTURE.md §2.2 Phase B step 6, Phase 6
"""

import logging
from typing import Dict, Optional, Tuple
from config import settings
from llm.base import BaseLLMProvider
from llm.mock_provider import MockLLMProvider
from llm.openai_provider import OpenAILLMProvider
from llm.gemini_provider import GeminiLLMProvider
from llm.anthropic_provider import AnthropicLLMProvider

logger = logging.getLogger("rag_engine.llm.factory")


# Providers hold HTTP clients with keep-alive pools: reuse them so each query skips a new TLS handshake.
_PROVIDER_CACHE: Dict[Tuple[str, Optional[str], bool], BaseLLMProvider] = {}


def get_llm_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
) -> BaseLLMProvider:
    """Cached provider per (provider, model, credentials present)."""
    target_provider = (provider_name or settings.llm_provider or "openai").lower()
    target_model = model_name or settings.llm_model
    has_key = bool({"openai": settings.openai_api_key, "gemini": settings.google_api_key,
                    "anthropic": settings.anthropic_api_key}.get(target_provider))
    key = (target_provider, target_model, has_key)
    if key not in _PROVIDER_CACHE:
        _PROVIDER_CACHE[key] = _build_llm_provider(target_provider, target_model)
    return _PROVIDER_CACHE[key]


def _build_llm_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
) -> BaseLLMProvider:
    """
    Factory resolving LLM provider instance based on runtime config and credential presence.
    Gracefully falls back to MockLLMProvider when API keys are absent in offline/test environments.
    """
    target_provider = (provider_name or settings.llm_provider or "openai").lower()
    target_model = model_name or settings.llm_model

    if target_provider == "mock":
        return MockLLMProvider(
            model_name=target_model or "mock-llm-v1",
            chunk_delay=settings.stream_chunk_delay,
        )

    if target_provider == "openai":
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY is not configured; falling back to MockLLMProvider.")
            return MockLLMProvider(
                model_name="mock-openai-fallback",
                chunk_delay=settings.stream_chunk_delay,
            )
        return OpenAILLMProvider(model_name=target_model)

    if target_provider == "gemini":
        if not settings.google_api_key:
            logger.warning("GOOGLE_API_KEY is not configured; falling back to MockLLMProvider.")
            return MockLLMProvider(
                model_name="mock-gemini-fallback",
                chunk_delay=settings.stream_chunk_delay,
            )
        return GeminiLLMProvider(model_name=target_model)

    if target_provider == "anthropic":
        if not settings.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY is not configured; falling back to MockLLMProvider.")
            return MockLLMProvider(
                model_name="mock-anthropic-fallback",
                chunk_delay=settings.stream_chunk_delay,
            )
        return AnthropicLLMProvider(model_name=target_model)

    logger.warning("Unknown LLM provider '%s'; defaulting to MockLLMProvider.", target_provider)
    return MockLLMProvider(
        model_name="mock-default",
        chunk_delay=settings.stream_chunk_delay,
    )
