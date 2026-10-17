"""
System Role: Startup warm-up — builds the cached embedding / LLM / reranker providers and their HTTP clients
             before the first request, so no user query pays SDK import or client construction costs.
Inputs: settings (provider selection & credentials).
Outputs: Populated provider caches; logs the warm-up duration.
Why: `import cohere` alone takes ~5.3 s in the container (it pulls in sagemaker/boto3); it used to run lazily
     inside the first rerank call of every uvicorn worker.
"""

import logging
import time

from embeddings.factory import get_embedding_provider
from llm.factory import get_llm_provider
from rerankers.factory import get_reranker_provider

logger = logging.getLogger("rag_engine.warmup")


def warm_up_providers() -> None:
    started = time.perf_counter()
    get_embedding_provider()
    get_llm_provider()
    reranker = get_reranker_provider()
    warm = getattr(reranker, "warm_up", None)
    if callable(warm):
        warm()
    logger.info("🔥 Providers warmed up in %.0f ms (%s).", (time.perf_counter() - started) * 1000, type(reranker).__name__)
