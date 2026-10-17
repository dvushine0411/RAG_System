"""
System Role: Automated integration test suite validating Phase 5 Augmentation & Prompt Engineering pipeline.
Inputs: Synthetic queries, retrieved chunk DTOs, and conversation history turns.
Outputs: Assertion validations confirming strict grounding, citation numbering [1], [2], chunk-level token truncation, and API endpoints.
Ref: ARCHITECTURE.md §2.2 Phase B step 5, §6 Observability, Guardrails & Evaluation
"""

import io
import os
import sys
import uuid

# Ensure UTF-8 output on Windows console
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure rag_engine root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from fastapi.testclient import TestClient
from api.main import app
from prompting.system_prompt import build_system_prompt, DEFAULT_ROLE_DESCRIPTION
from prompting.context_assembler import assemble_context
from prompting.token_budget import TokenBudgetManager
from prompting.augmenter import PromptAugmenter
from schemas.augmentation import AugmentationRequest, ChatMessageDTO
from schemas.retrieval import ScoredChunkDTO


def run_augmentation_tests():
    print("=================================================================")
    print("      PHASE 5 AUGMENTATION & PROMPT ENGINEERING TEST SUITE       ")
    print("=================================================================\n")

    # ──────────────────────────────────────────────────────────
    # TEST 1: System Prompt Grounding & Anti-Hallucination Guardrails
    # ──────────────────────────────────────────────────────────
    print("[TEST 1] Testing System Prompt Generation & Anti-Hallucination Directives...")
    default_prompt = build_system_prompt()
    assert DEFAULT_ROLE_DESCRIPTION in default_prompt
    assert "STRICT GROUNDING & SOURCE ATTRIBUTION" in default_prompt
    assert "HONEST REFUSAL (ANTI-HALLUCINATION GUARDRAIL)" in default_prompt
    assert "PROMPT INJECTION DEFENSE" in default_prompt
    assert "Dựa trên tài liệu được cung cấp, tôi không tìm thấy thông tin" in default_prompt

    # Test custom role override
    custom_role = "You are a specialized Legal Compliance Auditor."
    custom_prompt = build_system_prompt(custom_role=custom_role)
    assert custom_role in custom_prompt
    assert "STRICT GROUNDING & SOURCE ATTRIBUTION" in custom_prompt
    print("✅ TEST 1 PASSED: Modular system prompt includes strict anti-hallucination and security directives.\n")

    # ──────────────────────────────────────────────────────────
    # TEST 2: Context Assembler with Numbered Citations [1], [2]
    # ──────────────────────────────────────────────────────────
    print("[TEST 2] Testing Context Assembler & Citation Catalogs...")
    chunk_1 = ScoredChunkDTO(
        id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        chunk_index=0,
        content="HNSW graphs construct multi-layer proximity graphs for logarithmic nearest neighbor search.",
        token_count=18,
        source_type="pdf",
        page_number=1,
        section_title="Vector Indexing",
        vector_score=0.91,
        rerank_score=0.95,
        final_score=0.95,
        metadata={"title": "Vector_DB_Architecture.pdf"},
    )
    chunk_2 = ScoredChunkDTO(
        id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        chunk_index=1,
        content="Cross-encoder rerankers apply all-to-all cross attention over query and candidate chunks.",
        token_count=16,
        source_type="markdown",
        page_number=None,
        section_title="Two-Stage Retrieval",
        vector_score=0.85,
        rerank_score=0.89,
        final_score=0.89,
        metadata={"filename": "reranker_guide.md"},
    )

    context_block, citations = assemble_context([chunk_1, chunk_2])

    assert "<context>" in context_block and "</context>" in context_block
    assert "[1] Source: Vector_DB_Architecture.pdf | Section: Vector Indexing | Page: 1" in context_block
    assert "[2] Source: reranker_guide.md | Section: Two-Stage Retrieval" in context_block
    assert len(citations) == 2
    assert citations[0].citation_id == 1
    assert citations[0].chunk_id == chunk_1.id
    assert citations[0].title == "Vector_DB_Architecture.pdf"
    assert citations[1].citation_id == 2
    assert citations[1].chunk_id == chunk_2.id

    # Test empty context
    empty_block, empty_citations = assemble_context([])
    assert "(No relevant documents retrieved.)" in empty_block
    assert len(empty_citations) == 0
    print("✅ TEST 2 PASSED: Context block assembled with [1], [2] citation tags and provenance metadata.\n")

    # ──────────────────────────────────────────────────────────
    # TEST 3: Token Budget Manager & Priority Chunk Truncation
    # ──────────────────────────────────────────────────────────
    print("[TEST 3] Testing Token Budget Manager & Dynamic Truncation...")
    budget_mgr = TokenBudgetManager(max_context_tokens=1000, reserved_output_tokens=200)

    # Candidate chunks with distinct scores
    chunks_pool = [
        chunk_2,  # score 0.89
        chunk_1,  # score 0.95 (should be prioritized over chunk_2)
    ]
    query = "How does HNSW and reranking work?"
    history = [
        ChatMessageDTO(role="user", content="Hi, what can you help me with?"),
        ChatMessageDTO(role="assistant", content="I can answer questions based on your documents."),
    ]

    accepted, pruned_hist, report = budget_mgr.allocate_budget(
        system_prompt=default_prompt,
        query=query,
        candidate_chunks=chunks_pool,
        conversation_history=history,
    )

    assert len(accepted) == 2
    assert accepted[0].id == chunk_1.id, "Highest scored chunk must be first in accepted list"
    assert report.total_prompt_tokens <= (1000 - 200)
    assert report.chunks_included == 2
    assert report.chunks_truncated == 0

    # Test tight budget triggering chunk truncation
    tight_budget_mgr = TokenBudgetManager(max_context_tokens=520, reserved_output_tokens=150)
    accepted_tight, _, tight_report = tight_budget_mgr.allocate_budget(
        system_prompt=default_prompt,
        query=query,
        candidate_chunks=chunks_pool,
    )
    # Under a very tight budget, lower-ranked chunk is pruned
    assert tight_report.chunks_truncated >= 1 or tight_report.chunks_included <= 1
    print(f"  -> Budget allocation: System={report.system_tokens}, Query={report.query_tokens}, Context={report.context_tokens}")
    print("✅ TEST 3 PASSED: Token budget calculated and chunk priority truncation verified.\n")

    # ──────────────────────────────────────────────────────────
    # TEST 4: PromptAugmenter Orchestrator End-to-End
    # ──────────────────────────────────────────────────────────
    print("[TEST 4] Testing PromptAugmenter End-to-End Orchestrator...")
    augmenter = PromptAugmenter()
    req = AugmentationRequest(
        query=query,
        chunks=[chunk_1, chunk_2],
        conversation_history=history,
        max_context_tokens=4096,
        reserved_output_tokens=1024,
    )
    res = augmenter.assemble(req)

    assert len(res.assembled_messages) == 4  # 1 system + 2 history + 1 user
    assert res.assembled_messages[0].role == "system"
    assert res.assembled_messages[1].role == "user"
    assert res.assembled_messages[2].role == "assistant"
    assert res.assembled_messages[3].role == "user"
    assert "<context>" in res.assembled_messages[3].content
    assert "User Question:\n" in res.assembled_messages[3].content
    assert len(res.citations) == 2
    print("✅ TEST 4 PASSED: PromptAugmenter successfully constructed ordered chat message pipeline.\n")

    # ──────────────────────────────────────────────────────────
    # TEST 5: FastAPI Augmentation Endpoint
    # ──────────────────────────────────────────────────────────
    print("[TEST 5] Testing FastAPI POST /api/v1/augmentation/assemble...")
    client = TestClient(app)

    payload = {
        "query": "Explain HNSW logarithmic search.",
        "chunks": [
            {
                "id": chunk_1.id,
                "document_id": chunk_1.document_id,
                "chunk_index": 0,
                "content": chunk_1.content,
                "token_count": chunk_1.token_count,
                "source_type": chunk_1.source_type,
                "page_number": chunk_1.page_number,
                "section_title": chunk_1.section_title,
                "vector_score": chunk_1.vector_score,
                "final_score": chunk_1.final_score,
                "metadata": chunk_1.metadata,
            }
        ],
        "max_context_tokens": 4096,
        "reserved_output_tokens": 1024,
    }

    api_res = client.post("/api/v1/augmentation/assemble", json=payload)
    assert api_res.status_code == 200, f"Expected 200, got {api_res.status_code}: {api_res.text}"
    data = api_res.json()
    assert data["query"] == payload["query"]
    assert len(data["assembled_messages"]) == 2  # system + user
    assert len(data["citations"]) == 1
    assert data["citations"][0]["citation_id"] == 1
    assert data["budget_report"]["chunks_included"] == 1

    # Validation rejection for empty query
    bad_res = client.post("/api/v1/augmentation/assemble", json={"query": ""})
    assert bad_res.status_code == 422
    print("✅ TEST 5 PASSED: FastAPI /api/v1/augmentation/assemble returned 200 OK with valid schema.\n")

    print("=================================================================")
    print("   ALL PHASE 5 AUGMENTATION TESTS COMPLETED & VERIFIED (100%)   ")
    print("=================================================================")


if __name__ == "__main__":
    run_augmentation_tests()
