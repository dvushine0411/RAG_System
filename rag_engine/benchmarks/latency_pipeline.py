"""
System Role: Per-stage latency benchmark of the real query path — embed -> vector search -> rerank -> prompt
             assembly -> LLM time-to-first-token / total — with real providers.
Inputs: --dataset (questions from evaluation/datasets), --chunk (eval collection), --n, --top-k/--top-n,
        --cold (rebuild provider/HTTP clients before every query = behaviour before client caching).
Outputs: Console table of p50/p95 per stage + reports/latency_<mode>_<timestamp>.json.
Note: queries are paced by settings.eval_rerank_min_interval_seconds (Cohere trial limit); pacing is NOT timed.
Usage: docker compose run --rm -v ./rag_engine:/app rag_engine python -m benchmarks.latency_pipeline --n 8 [--cold]
"""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import llm.factory as llm_factory
import rerankers.factory as rr_factory
from config import settings
from evaluation.candidates import RateLimiter
from evaluation.corpus import ChunkConfig, use_config
from evaluation.dataset_builder import load_dataset
from generation.query_pipeline import RAGQueryPipeline
from llm.factory import get_llm_provider
from rerankers.factory import get_reranker_provider
from retrieval.retriever import VectorRetriever
from schemas.retrieval import RetrievalQueryRequest
from vectordb.qdrant_client import close_qdrant_client

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def pct(values: List[float], p: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="main")
    ap.add_argument("--chunk", default="512:64:0")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--top-k", type=int, default=settings.retrieval_top_k)
    ap.add_argument("--top-n", type=int, default=settings.rerank_top_n)
    ap.add_argument("--model", default=None)
    ap.add_argument("--cold", action="store_true", help="new provider + HTTP clients for every query")
    args = ap.parse_args()

    items = [i for i in load_dataset(args.dataset) if not i.get("history")][: args.n]
    limiter = RateLimiter(settings.eval_rerank_min_interval_seconds)
    stages: Dict[str, List[float]] = {k: [] for k in ("embed_search", "rerank", "augment", "llm_ttft", "llm_total", "ttft_total", "total")}

    with use_config(ChunkConfig.parse(args.chunk)):
        pipeline = RAGQueryPipeline()
        for i, item in enumerate(items, 1):
            await limiter.wait()
            if args.cold:
                llm_factory._PROVIDER_CACHE.clear()
                rr_factory._PROVIDER_CACHE.clear()
                pipeline.retriever = VectorRetriever()

            t0 = time.perf_counter()
            stage1 = await pipeline.retriever.retrieve_and_rerank(
                RetrievalQueryRequest(query=item["question"], top_k=args.top_k, top_n=args.top_k, rerank=False, rerank_min_score=0.0)
            )
            t1 = time.perf_counter()
            reranked = await get_reranker_provider().rerank(query=item["question"], chunks=stage1.results, top_n=args.top_n)
            t2 = time.perf_counter()
            augmented = pipeline.augment(item["question"], reranked, None, None)
            t3 = time.perf_counter()
            first = None
            async for _ in get_llm_provider(model_name=args.model).generate_stream(messages=augmented.assembled_messages):
                if first is None:
                    first = time.perf_counter()
            t4 = time.perf_counter()

            ms = lambda a, b: (b - a) * 1000
            row = {
                "embed_search": ms(t0, t1), "rerank": ms(t1, t2), "augment": ms(t2, t3),
                "llm_ttft": ms(t3, first or t4), "llm_total": ms(t3, t4), "ttft_total": ms(t0, first or t4), "total": ms(t0, t4),
            }
            for k, v in row.items():
                stages[k].append(v)
            print(f"  {i}/{len(items)} ttft {row['ttft_total']:.0f} ms (embed+search {row['embed_search']:.0f}, rerank {row['rerank']:.0f}, llm first token {row['llm_ttft']:.0f}) total {row['total']:.0f} ms")

    summary = {k: {"p50": pct(v, 0.5), "p95": pct(v, 0.95), "mean": round(sum(v) / len(v), 1)} for k, v in stages.items()}
    mode = "cold" if args.cold else "warm"
    print(f"\n{mode} — {len(items)} queries, model {args.model or settings.llm_model}, top_k {args.top_k}, top_n {args.top_n}")
    for k, v in summary.items():
        print(f"  {k:<13} p50 {v['p50']:>7} ms   p95 {v['p95']:>7} ms")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (REPORT_DIR / f"latency_{mode}_{stamp}.json").write_text(json.dumps({"args": vars(args), "summary": summary, "raw": stages}, indent=2))
    await close_qdrant_client()


if __name__ == "__main__":
    asyncio.run(main())
