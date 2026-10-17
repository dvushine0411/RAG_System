"""
System Role: End-to-end RAG query orchestrator tying query rewriting, retrieval, prompt augmentation,
             LLM streaming, and SSE formatting. Its steps are public so evaluation/ runs exactly the same code.
Inputs: QueryStreamRequest (prompt, history, filter, overrides) + optional PipelineOptions (eval overrides).
Outputs: AsyncIterator yielding wire-formatted Server-Sent Events ('citations' -> 'token'* -> 'done').
Flow: resolve_retrieval_query (query_rewriter) -> retrieve (VectorRetriever) -> augment (PromptAugmenter)
      -> LLM provider generate_stream -> sse_event_generator
Ref: ARCHITECTURE.md §2.2 Phase B step 1-7, Phase 6, Phase 8
"""

import logging
from dataclasses import dataclass
from typing import AsyncIterator, List, Optional

from config import settings
from generation.query_rewriter import rewrite_query
from generation.streamer import format_sse_frame, sse_event_generator
from llm.factory import get_llm_provider
from prompting.augmenter import PromptAugmenter
from retrieval.retriever import VectorRetriever
from schemas.augmentation import AugmentationRequest, AugmentedPromptResponse, ChatMessageDTO
from schemas.generation import QueryStreamRequest
from schemas.retrieval import RetrievalFilter, RetrievalQueryRequest, ScoredChunkDTO

logger = logging.getLogger("rag_engine.generation.query_pipeline")


@dataclass
class PipelineOptions:
    """Per-call overrides; None means "use the request value, else settings"."""

    query_rewrite: Optional[bool] = None
    rerank_min_score: Optional[float] = None


class RAGQueryPipeline:
    """
    Coordinates the full Retrieval-Augmented Generation execution:
    User Query -> (Query Rewriter) -> VectorRetriever -> PromptAugmenter -> LLM Provider -> SSE Event Stream.
    """

    def __init__(self) -> None:
        self.retriever = VectorRetriever()
        self.augmenter = PromptAugmenter()

    async def resolve_retrieval_query(
        self,
        query: str,
        history: Optional[List[ChatMessageDTO]],
        options: Optional[PipelineOptions] = None,
    ) -> str:
        enabled = options.query_rewrite if options and options.query_rewrite is not None else settings.query_rewrite_enabled
        if not enabled or not history:
            return query
        return await rewrite_query(query, history)

    async def retrieve(
        self,
        retrieval_query: str,
        filter: Optional[RetrievalFilter],
        top_k: Optional[int],
        top_n: Optional[int],
        options: Optional[PipelineOptions] = None,
    ) -> List[ScoredChunkDTO]:
        request = RetrievalQueryRequest(
            query=retrieval_query,
            filter=filter,
            top_k=top_k,
            top_n=top_n,
            rerank_min_score=options.rerank_min_score if options else None,
        )
        try:
            return (await self.retriever.retrieve_and_rerank(request)).results
        except Exception as ret_err:
            logger.warning("Vector retrieval unavailable (%s); proceeding with empty context fallback.", ret_err)
            return []

    def augment(
        self,
        query: str,
        chunks: List[ScoredChunkDTO],
        history: Optional[List[ChatMessageDTO]],
        max_tokens: Optional[int],
    ) -> AugmentedPromptResponse:
        return self.augmenter.assemble(
            AugmentationRequest(
                query=query,
                chunks=chunks,
                conversation_history=history,
                reserved_output_tokens=max_tokens,
            )
        )

    async def execute_stream(
        self,
        request: QueryStreamRequest,
        options: Optional[PipelineOptions] = None,
    ) -> AsyncIterator[str]:
        """
        Execute end-to-end RAG pipeline and yield Server-Sent Events.
        """
        try:
            # 1. Standalone retrieval query (follow-up questions only)
            retrieval_query = await self.resolve_retrieval_query(request.query, request.conversation_history, options)

            # 2. Retrieve & Rerank Chunks with outage resilience
            chunks = await self.retrieve(
                retrieval_query, request.filter, request.retrieval_top_k, request.rerank_top_n, options
            )

            # 3. Augment Prompt & Budget Tokens (the LLM answers the ORIGINAL question)
            augmented = self.augment(request.query, chunks, request.conversation_history, request.max_tokens)

            # 4. Stream Tokens from LLM
            provider = get_llm_provider(model_name=request.model)
            token_stream = provider.generate_stream(
                messages=augmented.assembled_messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )

            # 5. Format & Yield SSE Frames
            async for sse_frame in sse_event_generator(
                token_stream=token_stream,
                citations=augmented.citations,
                prompt_tokens=augmented.budget_report.total_prompt_tokens,
                retrieval_query=retrieval_query if retrieval_query != request.query else None,
            ):
                yield sse_frame

        except Exception as exc:
            logger.error("RAG query pipeline execution error: %s", exc)
            yield format_sse_frame(
                "error",
                {"message": str(exc), "error_code": "RAG_PIPELINE_ERROR"},
            )
