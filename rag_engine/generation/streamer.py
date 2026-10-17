"""
System Role: Server-Sent Events (SSE) serializer and streaming lifecycle orchestrator.
Inputs: Token stream AsyncIterator, citation provenance list, and token consumption metrics.
Outputs: Text chunks formatted as standard SSE frames ('citations', 'token', 'done', 'error').
Ref: ARCHITECTURE.md §2.2 Phase B step 7, Phase 6
"""

import json
import logging
import re
import time
from typing import AsyncIterator, List, Optional

from schemas.augmentation import CitationMetadata
from schemas.generation import (
    StreamCitationsData,
    StreamDoneData,
    StreamErrorData,
    StreamTokenData,
    TokenUsageDTO,
)

logger = logging.getLogger("rag_engine.generation.streamer")


def format_sse_frame(event: str, data: dict | str) -> str:
    """
    Format event name and payload into standard SSE wire format.
    Wire format:
    event: <event_name>\n
    data: <json_string>\n\n
    """
    if isinstance(data, dict):
        payload_str = json.dumps(data, ensure_ascii=False)
    else:
        payload_str = str(data)
    return f"event: {event}\ndata: {payload_str}\n\n"


_CITATION_MARKER = re.compile(r"\[(\d+)\]")


def extract_used_citations(text: str, citations: Optional[List[CitationMetadata]]) -> List[int]:
    """Ids of [n] markers present in the answer that map to a provided citation."""
    valid = {c.citation_id for c in citations or []}
    return sorted({int(n) for n in _CITATION_MARKER.findall(text)} & valid)


async def sse_event_generator(
    token_stream: AsyncIterator[str],
    citations: Optional[List[CitationMetadata]] = None,
    prompt_tokens: int = 0,
    retrieval_query: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Wrap an asynchronous token stream into ordered Server-Sent Events.

    Lifecycle:
    1. Emit 'citations' event at stream start (if available) for immediate UI badge rendering.
    2. Stream continuous 'token' events containing text deltas.
    3. Emit 'done' event at the end with token usage metrics and latency calculation.
    4. Emit 'error' event and re-raise if an exception interrupts streaming.
    """
    start_time = time.perf_counter()
    accumulated_tokens: List[str] = []

    try:
        # Step 1: Emit citations event at the start
        if citations:
            citations_payload = StreamCitationsData(citations=citations).model_dump()
            yield format_sse_frame("citations", citations_payload)

        # Step 2: Stream tokens as they arrive
        async for delta in token_stream:
            if not delta:
                continue
            accumulated_tokens.append(delta)
            token_payload = StreamTokenData(delta=delta).model_dump()
            yield format_sse_frame("token", token_payload)

        # Step 3: Compute final metrics and emit 'done'
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        full_text = "".join(accumulated_tokens)
        # Approximate completion token count (1 token ≈ 4 chars or whitespace segments)
        completion_tokens = max(1, len(full_text.split())) if full_text.strip() else 0

        usage = TokenUsageDTO(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        done_payload = StreamDoneData(
            finish_reason="stop",
            token_usage=usage,
            latency_ms=duration_ms,
            used_citation_ids=extract_used_citations(full_text, citations),
            retrieval_query=retrieval_query,
        ).model_dump()
        yield format_sse_frame("done", done_payload)

    except Exception as exc:
        logger.error("SSE stream interrupted by error: %s", exc)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        error_payload = StreamErrorData(
            message=str(exc),
            error_code="STREAM_GENERATION_FAILED",
        ).model_dump()
        yield format_sse_frame("error", error_payload)
        raise exc
