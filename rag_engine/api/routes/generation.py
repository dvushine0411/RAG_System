"""
System Role: FastAPI route handlers exposing standalone LLM generation and full RAG query streaming endpoints.
Inputs: GenerateStreamRequest or QueryStreamRequest via JSON HTTP POST.
Outputs: StreamingResponse with Server-Sent Events (media_type="text/event-stream").
Ref: ARCHITECTURE.md §2.2 Phase B step 6-7, Phase 6
"""

import logging
from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from schemas.generation import GenerateStreamRequest, QueryStreamRequest
from llm.factory import get_llm_provider
from generation.streamer import sse_event_generator
from generation.query_pipeline import RAGQueryPipeline

logger = logging.getLogger("rag_engine.api.generation")

router = APIRouter(prefix="/api/v1", tags=["LLM Generation & Streaming"])


@router.post(
    "/generate/stream",
    summary="Stream LLM generation for pre-assembled messages (SSE)",
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
)
async def generate_stream_endpoint(request: GenerateStreamRequest):
    """
    Direct prompt generation endpoint streaming Server-Sent Events.
    Emits citations (if provided) followed by tokens and a done event.
    """
    logger.info("Received direct generation request with %d messages", len(request.messages))
    provider = get_llm_provider(model_name=request.model)

    token_stream = provider.generate_stream(
        messages=request.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )

    # Estimate input tokens heuristically if budget report is absent
    estimated_prompt_tokens = sum(len(m.content.split()) for m in request.messages)

    sse_generator = sse_event_generator(
        token_stream=token_stream,
        citations=request.citations,
        prompt_tokens=estimated_prompt_tokens,
    )

    return StreamingResponse(
        sse_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/query/stream",
    summary="End-to-End RAG query stream: Retrieve -> Augment -> Stream (SSE)",
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
)
async def query_stream_endpoint(request: QueryStreamRequest):
    """
    Unified RAG pipeline streaming endpoint. Executes two-stage vector retrieval,
    prompt augmentation with citation grounding, and streams Server-Sent Events.
    """
    logger.info("Received RAG query stream request: '%s'", request.query[:60])
    pipeline = RAGQueryPipeline()

    return StreamingResponse(
        pipeline.execute_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
