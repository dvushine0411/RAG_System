"""
System Role: Offline unit tests for Phase 8 building blocks (no API keys, no network, no Qdrant).
Inputs: Synthetic chunks / texts.
Outputs: Exit code 0 when all assertions pass. Covers evidence relevance labels, retrieval metrics (incl. nDCG with
         multiple relevant chunks), offline config simulation, cost budget guard, used-citation extraction,
         contextual header, OCR fence cleanup, system prompt v1/v2 switch, and the mock-safe query rewriter.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from evaluation.candidates import CandidateCache, RetrievalConfig, relevance_flags
from evaluation.cost_tracker import BudgetExceeded, CostTracker
from evaluation.evidence import evidence_in_text, evidence_recall, is_relevant
from evaluation.retrieval_metrics import hit_at, ndcg_at, reciprocal_rank
from generation.query_rewriter import rewrite_query
from generation.streamer import extract_used_citations
from ingestion.contextual_header import build_context_header, with_header
from ingestion.pdf_ocr import _clean
from prompting.system_prompt import build_system_prompt
from schemas.augmentation import ChatMessageDTO, CitationMetadata
from schemas.retrieval import ScoredChunkDTO


def chunk(cid: str, content: str, vector: float, rerank=None) -> ScoredChunkDTO:
    return ScoredChunkDTO(id=cid, document_id="d", chunk_index=0, content=content, token_count=len(content.split()),
                          source_type="pdf", vector_score=vector, rerank_score=rerank, final_score=vector, metadata={})


def test_evidence() -> None:
    ev = "Chủ tịch Hồ Chí Minh đọc Tuyên ngôn Độc lập"
    assert evidence_in_text(ev, "Ngày 2-9-1945, Chủ tịch  Hồ Chí Minh đọc Tuyên ngôn Độc lập tại Ba Đình.")
    assert not evidence_in_text(ev, "Hồ Chí Minh đọc bản tuyên ngôn")
    assert abs(evidence_recall(ev, "Hồ Chí Minh đọc Tuyên ngôn") - 0.6) < 1e-9  # 6 of 10 tokens
    assert is_relevant(ev, "… Chủ tịch Hồ Chí Minh đọc Tuyên ngôn Độc lập …") and not is_relevant(ev, "Tắt đèn của Ngô Tất Tố")
    print("  PASS evidence matching (Vietnamese NFC, verbatim + recall)")


def test_metrics() -> None:
    assert hit_at([False, True, False], 2) == 1.0 and hit_at([False, False, True], 2) == 0.0
    assert reciprocal_rank([False, True]) == 0.5 and reciprocal_rank([False, False]) == 0.0
    assert abs(ndcg_at([True], 3) - 1.0) < 1e-9
    assert abs(ndcg_at([True, True], 3) - 1.0) < 1e-9, "two relevant chunks at the top must not exceed 1"
    assert 0 < ndcg_at([False, True], 3) < 1
    print("  PASS retrieval metrics (nDCG ≤ 1 with overlapping evidence)")


def test_simulate() -> None:
    pool = [chunk("a", "x", 0.9, 0.01), chunk("b", "y", 0.8, 0.95), chunk("c", "z", 0.7, 0.50), chunk("d", "w", 0.1, 0.99)]
    out = CandidateCache.simulate(pool, RetrievalConfig(top_k=3, top_n=2, min_score=0.0))
    assert [c.id for c in out] == ["b", "c"], "d is outside the vector top_k, a is reranked down"
    out = CandidateCache.simulate(pool, RetrievalConfig(top_k=4, top_n=3, min_score=0.6))
    assert [c.id for c in out] == ["d", "b"] and out[0].final_score == 0.99
    assert relevance_flags(out, None) == [False, False]
    print("  PASS offline retrieval-config simulation")


def test_budget() -> None:
    t = CostTracker(budget_usd=0.001)
    t.add("gpt-4o-mini", 1000, 100)
    try:
        t.add("gpt-4o-mini", 10_000, 1000)
        raise AssertionError("budget not enforced")
    except BudgetExceeded:
        pass
    assert t.summary()["by_model"]["gpt-4o-mini"]["calls"] == 2
    print("  PASS cost tracker budget guard")


def test_citations_header_ocr_prompt() -> None:
    cites = [CitationMetadata(citation_id=i, chunk_id=f"c{i}", document_id="d", score=0.5) for i in (1, 2, 3)]
    assert extract_used_citations("A [1]. B [3][1]. C [9].", cites) == [1, 3]

    saved = settings.chunk_context_header_enabled
    settings.chunk_context_header_enabled = True
    h = build_context_header("Tắt đèn.pdf", {"page_number": 12, "section_title": "Chương 1"})
    assert h == "Document: Tắt đèn.pdf > Section: Chương 1 > Page: 12" and with_header(h, "abc").endswith("\nabc")
    settings.chunk_context_header_enabled = False
    assert build_context_header("x.pdf", {"page_number": 1}) == "" and with_header("", "abc") == "abc"
    settings.chunk_context_header_enabled = saved

    assert _clean("```\nLỊCH SỬ 12\n```") == "LỊCH SỬ 12" and _clean("plain") == "plain"

    saved_v = settings.system_prompt_version
    settings.system_prompt_version = "v2"
    v2 = build_system_prompt()
    settings.system_prompt_version = "v1"
    v1 = build_system_prompt()
    settings.system_prompt_version = saved_v
    assert "Refuse ONLY when no passage" in v2 and "Refuse ONLY when no passage" not in v1
    assert "HONEST REFUSAL" in v1 and "HONEST REFUSAL" in v2
    print("  PASS used-citation extraction, contextual header, OCR cleanup, prompt v1/v2")


def test_rewriter_mock_safe() -> None:
    hist = [ChatMessageDTO(role="user", content="Tắt đèn là gì?"), ChatMessageDTO(role="assistant", content="Tiểu thuyết.")]
    assert asyncio.run(rewrite_query("Ai viết nó?", [])) == "Ai viết nó?"
    if settings.llm_provider == "mock" or not settings.openai_api_key:
        assert asyncio.run(rewrite_query("Ai viết nó?", hist)) == "Ai viết nó?", "mock output must never replace the query"
    print("  PASS query rewriter is a no-op without history / under mock LLM")


if __name__ == "__main__":
    print("=== Phase 8 offline tests ===")
    test_evidence()
    test_metrics()
    test_simulate()
    test_budget()
    test_citations_header_ocr_prompt()
    test_rewriter_mock_safe()
    print("\n[SUCCESS] ALL PHASE 8 OFFLINE TESTS PASSED")
