"""
System Role: Integration test suite validating Phase 6 LLM Generation, Provider Factory, and SSE Streaming pipeline.
Inputs: Synthetic test queries, chat messages, and citation payloads.
Outputs: Assertion verifications for token streaming, SSE event protocols, citation emission, and FastAPI routes.
Ref: ARCHITECTURE.md §2.2 Phase B step 6-7, Phase 6
"""

import asyncio
import io
import json
import os
import sys

# Force UTF-8 on Windows terminal for emoji/unicode assertion output
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure rag_engine root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport

from config import settings
from schemas.augmentation import ChatMessageDTO, CitationMetadata
from schemas.generation import GenerateStreamRequest, QueryStreamRequest
from llm.mock_provider import MockLLMProvider
from llm.factory import get_llm_provider
from generation.streamer import format_sse_frame, sse_event_generator
from generation.query_pipeline import RAGQueryPipeline
from retrieval.retriever import VectorRetriever
from api.main import app


async def test_mock_llm_provider_streaming():
    """
    Verify MockLLMProvider yields tokens and embeds citation tags properly.
    """
    print("\n[Test 1] Testing MockLLMProvider streaming with citations...")
    provider = MockLLMProvider(model_name="test-mock", chunk_delay=0.0)
    messages = [
        ChatMessageDTO(role="system", content="System instruction."),
        ChatMessageDTO(
            role="user",
            content="<context>\n[1] Document chunk about HNSW indexing.\n</context>\nHNSW hoạt động như thế nào?",
        ),
    ]

    tokens: list[str] = []
    async for token in provider.generate_stream(messages):
        tokens.append(token)

    full_output = "".join(tokens)
    print(f"  Mock Output: {full_output}")

    assert len(tokens) > 0, "Provider should stream multiple token chunks"
    assert "[1]" in full_output, "Grounded response must cite source tag [1]"
    assert "HNSW" in full_output, "Response must refer to queried concepts"
    print("  ✅ PASS: MockLLMProvider streams tokens with grounded citations.")


async def test_mock_llm_provider_empty_context_refusal():
    """
    Verify MockLLMProvider emits honest refusal when context is missing.
    """
    print("\n[Test 2] Testing MockLLMProvider empty context honest refusal...")
    provider = MockLLMProvider(model_name="test-mock", chunk_delay=0.0)
    messages = [
        ChatMessageDTO(role="system", content="System instruction."),
        ChatMessageDTO(role="user", content="Câu hỏi không có context"),
    ]

    tokens: list[str] = []
    async for token in provider.generate_stream(messages):
        tokens.append(token)

    full_output = "".join(tokens)
    assert "không tìm thấy thông tin" in full_output.lower()
    print("  ✅ PASS: MockLLMProvider properly emits honest refusal when context is missing.")


async def test_sse_event_generator_protocol():
    """
    Verify SSE event generator follows strict wire protocol:
    1. 'citations' event at start
    2. Continuous 'token' events
    3. Final 'done' event with metrics
    """
    print("\n[Test 3] Testing SSE wire framing protocol ('citations' -> 'token'* -> 'done')...")
    async def sample_token_stream():
        for tok in ["Xin ", "chào ", "RAG ", "System!"]:
            yield tok

    citations = [
        CitationMetadata(
            citation_id=1,
            chunk_id="chunk-uuid-123",
            document_id="doc-uuid-456",
            title="Kiến trúc RAG",
            source_type="pdf",
            page_number=3,
            section_title="Tổng quan",
            score=0.95,
        )
    ]

    frames: list[str] = []
    async for frame in sse_event_generator(
        token_stream=sample_token_stream(),
        citations=citations,
        prompt_tokens=50,
    ):
        frames.append(frame)

    assert len(frames) >= 3, "Stream must emit citations, tokens, and done frames"

    # Frame 0: citations
    assert frames[0].startswith("event: citations\n")
    citation_data_line = [l for l in frames[0].split("\n") if l.startswith("data: ")][0]
    citation_json = json.loads(citation_data_line[6:])
    assert len(citation_json["citations"]) == 1
    assert citation_json["citations"][0]["chunk_id"] == "chunk-uuid-123"

    # Intermediate frames: tokens
    token_frames = [f for f in frames if f.startswith("event: token\n")]
    assert len(token_frames) == 4
    token_text = "".join(
        json.loads([l for l in f.split("\n") if l.startswith("data: ")][0][6:])["delta"]
        for f in token_frames
    )
    assert token_text == "Xin chào RAG System!"

    # Final frame: done
    done_frame = frames[-1]
    assert done_frame.startswith("event: done\n")
    done_data_line = [l for l in done_frame.split("\n") if l.startswith("data: ")][0]
    done_json = json.loads(done_data_line[6:])
    assert done_json["finish_reason"] == "stop"
    assert done_json["token_usage"]["prompt_tokens"] == 50
    assert done_json["token_usage"]["completion_tokens"] > 0
    assert done_json["latency_ms"] >= 0.0
    print("  ✅ PASS: SSE event generator adheres strictly to event sequence and wire format.")


def test_llm_factory_fallback():
    """
    Verify LLM factory returns MockLLMProvider when provider is 'mock' or API keys are missing.
    """
    print("\n[Test 4] Testing LLM Factory provider resolution & fallback...")
    mock_prov = get_llm_provider(provider_name="mock")
    assert isinstance(mock_prov, MockLLMProvider)

    # Unknown provider falls back to mock
    unknown_prov = get_llm_provider(provider_name="non_existent_provider")
    assert isinstance(unknown_prov, MockLLMProvider)
    print("  ✅ PASS: LLM Factory correctly resolves and falls back to MockLLMProvider.")


async def test_api_generate_stream_endpoint():
    """
    Verify FastAPI POST /api/v1/generate/stream endpoint returns 200 text/event-stream.
    """
    print("\n[Test 5] Testing FastAPI POST /api/v1/generate/stream endpoint...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "messages": [
                {"role": "system", "content": "You are a test assistant."},
                {
                    "role": "user",
                    "content": "<context>\n[1] Chunk content\n</context>\nTest question",
                },
            ],
            "model": "mock",
        }
        res = await client.post("/api/v1/generate/stream", json=payload)
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

        body_text = res.text
        assert "event: token" in body_text
        assert "event: done" in body_text
        print("  ✅ PASS: /api/v1/generate/stream returns valid 200 SSE stream.")


async def test_api_query_stream_endpoint():
    """
    Verify FastAPI POST /api/v1/query/stream endpoint executes full RAG pipeline with SSE stream.
    """
    print("\n[Test 6] Testing FastAPI POST /api/v1/query/stream full pipeline...")
    from unittest.mock import patch
    from schemas.retrieval import RetrievalResponse, ScoredChunkDTO

    mock_chunk = ScoredChunkDTO(
        id="chunk-test-1",
        document_id="doc-test-1",
        chunk_index=0,
        content="HNSW là cấu trúc đồ thị đa tầng phục vụ tìm kiếm vector xấp xỉ.",
        token_count=16,
        source_type="pdf",
        page_number=1,
        section_title="Cơ chế HNSW",
        vector_score=0.96,
        rerank_score=0.98,
        final_score=0.98,
        metadata={},
    )
    mock_retrieval_res = RetrievalResponse(
        query="Hệ thống RAG hoạt động như thế nào?",
        total_candidates=1,
        returned_count=1,
        fallback_used=False,
        status="success",
        results=[mock_chunk],
    )

    from unittest.mock import AsyncMock, patch

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "query": "Hệ thống RAG hoạt động như thế nào?",
            "model": "mock",
        }
        with patch.object(VectorRetriever, "retrieve_and_rerank", new_callable=AsyncMock) as mock_method:
            mock_method.return_value = mock_retrieval_res
            res = await client.post("/api/v1/query/stream", json=payload)
            assert res.status_code == 200
            assert "text/event-stream" in res.headers["content-type"]

            body_text = res.text
            assert "event: citations" in body_text, "Pipeline must emit citations event"
            assert "event: token" in body_text, "Pipeline must stream tokens"
            assert "event: done" in body_text, "Pipeline must finish with done event"
            print("  ✅ PASS: /api/v1/query/stream returns valid 200 SSE stream with citations, tokens, and done.")


async def main():
    print("=================================================================")
    print("    RAG Engine Phase 6: LLM Generation & Streaming Test Suite    ")
    print("=================================================================")
    await test_mock_llm_provider_streaming()
    await test_mock_llm_provider_empty_context_refusal()
    await test_sse_event_generator_protocol()
    test_llm_factory_fallback()
    await test_api_generate_stream_endpoint()
    await test_api_query_stream_endpoint()
    print("\n=================================================================")
    print("  🎉 ALL 6 PHASE 6 INTEGRATION TESTS PASSED SUCCESSFULLY!        ")
    print("=================================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
