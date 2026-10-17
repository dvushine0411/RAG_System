"""
System Role: Phase 8 evaluation CLI — indexes eval corpora, builds the dataset, sweeps retrieval parameters
             offline (cached rerank), and runs end-to-end generation + LLM-judge evaluations with reports.
Inputs: Sub-commands and flags (see --help); eval corpus mounted at --corpus; settings.eval_*.
Outputs: reports/eval_<command>_<label>_<timestamp>.{json,md}; console summary incl. estimated API cost.
Usage (inside the compose network, code mounted):
  docker compose run --rm -v ./rag_engine:/app -v <docs>:/corpus:ro rag_engine python -m evaluation.run_eval <cmd> ...
  index           --corpus /corpus --chunk 512:64:0 [--rebuild]
  build-dataset   --chunk 512:64:0 --name main [--passages 18 --followups 6 --unanswerable 6]
  retrieval-sweep --dataset main --chunk 512:64:0 [--rewrite] [--top-k ...] [--top-n ...] [--min-score ...]
  generate-eval   --dataset main --chunk 512:64:0 --top-k 20 --top-n 5 --min-score 0 [--model gpt-4o-mini] [--rewrite]
"""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from statistics import fmean
from typing import Dict, List, Optional

from config import settings
from evaluation.candidates import CACHE_DIR, CandidateCache, RetrievalConfig, relevance_flags
from evaluation.corpus import ChunkConfig, index_corpus, use_config
from evaluation.cost_tracker import TRACKER, BudgetExceeded
from evaluation.dataset_builder import build_dataset, load_dataset
from evaluation.llm_judge import judge
from evaluation.retrieval_metrics import aggregate, hit_at, ndcg_at, reciprocal_rank
from generation.query_pipeline import RAGQueryPipeline
from generation.query_rewriter import rewrite_query
from ingestion.chunking import count_tokens
from llm.factory import get_llm_provider
from rerankers.factory import get_reranker_provider
from schemas.augmentation import ChatMessageDTO
from vectordb.qdrant_client import close_qdrant_client
from ingestion import pdf_ocr

pdf_ocr.usage_hook = TRACKER.add  # OCR spend counts against the eval budget

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
REWRITE_CACHE = CACHE_DIR / "rewrites.json"


# ── helpers ──────────────────────────────────────────────────────────
def _history(item: dict) -> List[ChatMessageDTO]:
    return [ChatMessageDTO(**m) for m in item.get("history", [])]


async def retrieval_query(item: dict, rewrite: bool) -> str:
    """Rewritten standalone query for follow-ups (cached: deterministic and free on re-runs)."""
    if not rewrite or not item.get("history"):
        return item["question"]
    cache = json.loads(REWRITE_CACHE.read_text("utf-8")) if REWRITE_CACHE.exists() else {}
    key = f"{settings.query_rewrite_model or settings.llm_model}|{json.dumps(item['history'], ensure_ascii=False)}|{item['question']}"
    if key not in cache:
        cache[key] = await rewrite_query(item["question"], _history(item))
        TRACKER.add(settings.query_rewrite_model or settings.llm_model, 250, count_tokens(cache[key]))
        REWRITE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        REWRITE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache[key]


def write_report(kind: str, label: str, payload: dict, md_lines: List[str]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = REPORT_DIR / f"eval_{kind}_{label}_{stamp}"
    payload["cost"] = TRACKER.summary()
    base.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines += ["", f"_Estimated API cost of this run: ${TRACKER.total_usd():.4f} · Cohere rerank calls: {TRACKER.cohere_calls}_"]
    base.with_suffix(".md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return base.with_suffix(".md")


# ── commands ─────────────────────────────────────────────────────────
async def cmd_index(args) -> None:
    cfg = ChunkConfig.parse(args.chunk)
    print(f"Indexing {args.corpus} → '{cfg.collection}'")
    await index_corpus(Path(args.corpus), cfg, rebuild=args.rebuild, pattern=args.pattern)


async def cmd_build_dataset(args) -> None:
    cfg = ChunkConfig.parse(args.chunk)
    await build_dataset(cfg.collection, args.passages, args.followups, args.unanswerable, args.seed, args.name)


async def collect_pools(items: List[dict], cfg: ChunkConfig, rewrite: bool) -> Dict[str, list]:
    pools: Dict[str, list] = {}
    with use_config(cfg):
        cache = CandidateCache(cfg.collection)
        for i, item in enumerate(items, start=1):
            q = await retrieval_query(item, rewrite)
            pools[item["id"]] = await cache.pool(q)
            print(f"\r  candidate pools {i}/{len(items)}", end="", flush=True)
    print()
    return pools


async def cmd_retrieval_sweep(args) -> None:
    cfg = ChunkConfig.parse(args.chunk)
    items = load_dataset(args.dataset)
    pools = await collect_pools(items, cfg, args.rewrite)
    answerable = [i for i in items if i["type"] != "unanswerable"]
    unanswerable = [i for i in items if i["type"] == "unanswerable"]

    rows = []
    for k, n, s in product(args.top_k, args.top_n, args.min_score):
        if n > k:
            continue
        rc = RetrievalConfig(k, n, s)
        per_q, ctx_chunks, ctx_tokens = [], [], []
        for it in answerable:
            chosen = CandidateCache.simulate(pools[it["id"]], rc)
            rel = relevance_flags(chosen, it["evidence"])
            per_q.append({"hit": hit_at(rel, n), "mrr": reciprocal_rank(rel), "ndcg": ndcg_at(rel, n)})
            ctx_chunks.append(len(chosen))
            ctx_tokens.append(sum(c.token_count for c in chosen))
        empty_unans = [len(CandidateCache.simulate(pools[it["id"]], rc)) == 0 for it in unanswerable]
        m = aggregate(per_q)
        rows.append({
            "config": rc.label(), "top_k": k, "top_n": n, "min_score": s, **m,
            "avg_chunks": round(fmean(ctx_chunks), 2), "avg_context_tokens": round(fmean(ctx_tokens), 1),
            "unanswerable_empty_rate": round(fmean(empty_unans), 3) if empty_unans else None,
        })

    # Objective: keep the evidence (hit) first, rank it high (mrr), then prefer less context noise
    rows.sort(key=lambda r: (r["hit"], r["mrr"], -r["avg_context_tokens"]), reverse=True)
    label = f"{cfg.collection}{'_rw' if args.rewrite else ''}"
    md = [
        f"# Retrieval sweep — {label}",
        f"Dataset `{args.dataset}`: {len(answerable)} answerable + {len(unanswerable)} unanswerable questions; "
        f"candidate pool {settings.eval_candidate_pool}, reranker {type(get_reranker_provider()).__name__}.",
        "",
        "| config | Hit@N | MRR | nDCG@N | avg chunks | avg ctx tokens | unanswerable→empty |",
        "|---|---|---|---|---|---|---|",
        *[f"| {r['config']} | {r['hit']:.3f} | {r['mrr']:.3f} | {r['ndcg']:.3f} | {r['avg_chunks']} | {r['avg_context_tokens']} | {r['unanswerable_empty_rate']} |" for r in rows],
    ]
    path = write_report("retrieval", label, {"chunk": cfg.__dict__, "rewrite": args.rewrite, "rows": rows}, md)
    print("\n".join(md[4:14]))
    print(f"\nReport: {path}  |  est. cost ${TRACKER.total_usd():.4f}, Cohere calls {TRACKER.cohere_calls}")


async def answer_one(pipeline: RAGQueryPipeline, item: dict, chunks, model: Optional[str]) -> dict:
    history = _history(item)
    augmented = pipeline.augment(item["question"], chunks, history or None, None)
    provider = get_llm_provider(model_name=model)
    t0 = time.perf_counter()
    answer = "".join([d async for d in provider.generate_stream(messages=augmented.assembled_messages)])
    latency = (time.perf_counter() - t0) * 1000
    TRACKER.add(provider.model_name, augmented.budget_report.total_prompt_tokens, count_tokens(answer))
    scores = await judge(item["question"], augmented_chunks(augmented, chunks), answer, item.get("reference_answer"), item["type"] != "unanswerable")
    return {"answer": answer, "latency_ms": round(latency), "prompt_tokens": augmented.budget_report.total_prompt_tokens, **scores.to_dict()}


def augmented_chunks(augmented, chunks):
    """Chunks that survived the token budget, in citation order (what the LLM actually saw)."""
    by_id = {c.id: c for c in chunks}
    return [by_id[c.chunk_id] for c in augmented.citations if c.chunk_id in by_id]


def composite(r: dict, answerable: bool) -> float:
    if not answerable:
        return 0.6 * r["refusal_correct"] + 0.4 * r["groundedness"]
    return (0.35 * (r["correctness"] or 0) + 0.25 * r["groundedness"] + 0.15 * r["answer_relevance"]
            + 0.15 * r["context_relevance"] + 0.10 * r["refusal_correct"])


async def cmd_generate_eval(args) -> None:
    cfg = ChunkConfig.parse(args.chunk)
    items = load_dataset(args.dataset)
    if args.limit:
        items = items[: args.limit]
    pools = await collect_pools(items, cfg, args.rewrite)
    rc = RetrievalConfig(args.top_k, args.top_n, args.min_score)
    pipeline = RAGQueryPipeline()
    sem = asyncio.Semaphore(4)
    model = args.model or settings.llm_model

    async def run(item):
        async with sem:
            chunks = CandidateCache.simulate(pools[item["id"]], rc)
            r = await answer_one(pipeline, item, chunks, model)
            r.update({"id": item["id"], "type": item["type"], "question": item["question"],
                      "evidence_retrieved": any(relevance_flags(chunks, item["evidence"])) if item["evidence"] else None})
            r["score"] = round(composite(r, item["type"] != "unanswerable"), 4)
            return r

    with use_config(cfg):
        results = []
        for coro in asyncio.as_completed([run(i) for i in items]):
            results.append(await coro)
            print(f"\r  answered {len(results)}/{len(items)}  (est. ${TRACKER.total_usd():.3f})", end="", flush=True)
    print()
    results.sort(key=lambda r: r["id"])

    ans = [r for r in results if r["type"] != "unanswerable"]
    una = [r for r in results if r["type"] == "unanswerable"]
    mean = lambda rs, k: round(fmean(r[k] for r in rs if r[k] is not None), 4) if [r for r in rs if r[k] is not None] else None
    summary = {
        "overall_score": mean(results, "score"),
        "answerable": {k: mean(ans, k) for k in ("correctness", "groundedness", "answer_relevance", "context_relevance", "refusal_correct", "score")},
        "unanswerable": {k: mean(una, k) for k in ("refusal_correct", "groundedness", "score")},
        "by_type": {t: mean([r for r in results if r["type"] == t], "score") for t in sorted({r["type"] for r in results})},
        "latency_ms_avg": mean(results, "latency_ms"),
        "prompt_tokens_avg": mean(results, "prompt_tokens"),
    }
    label = f"{cfg.collection}_{rc.label()}_{model}{'_rw' if args.rewrite else ''}_p{settings.system_prompt_version}"
    md = [
        f"# Generation eval — {label}",
        f"Dataset `{args.dataset}` ({len(results)} items) · judge `{settings.eval_judge_model}`",
        "",
        f"**Overall score: {summary['overall_score']}**",
        "",
        "| answerable metric | value |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in summary["answerable"].items()],
        "", "| unanswerable metric | value |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in summary["unanswerable"].items()],
        "", "| by type | score |", "|---|---|", *[f"| {k} | {v} |" for k, v in summary["by_type"].items()],
        "", f"Latency avg {summary['latency_ms_avg']} ms · prompt tokens avg {summary['prompt_tokens_avg']}",
        "", "## Lowest-scoring answers", "",
        *[f"- **{r['id']}** ({r['type']}, {r['score']}): {r['question']} — _{r['rationale']}_" for r in sorted(results, key=lambda r: r["score"])[:8]],
    ]
    path = write_report("generation", label, {"config": {"chunk": cfg.__dict__, "retrieval": rc.__dict__, "model": model, "rewrite": args.rewrite, "system_prompt_version": settings.system_prompt_version}, "summary": summary, "results": results}, md)
    print("\n".join(md[3:]))
    print(f"\nReport: {path}  |  est. cost ${TRACKER.total_usd():.4f}, Cohere calls {TRACKER.cohere_calls}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("index"); s.add_argument("--corpus", required=True); s.add_argument("--chunk", default="512:64:0"); s.add_argument("--rebuild", action="store_true"); s.add_argument("--pattern", default="*")
    s = sub.add_parser("build-dataset"); s.add_argument("--chunk", default="512:64:0"); s.add_argument("--name", default="main")
    s.add_argument("--passages", type=int, default=18); s.add_argument("--followups", type=int, default=6); s.add_argument("--unanswerable", type=int, default=6); s.add_argument("--seed", type=int, default=7)
    s = sub.add_parser("retrieval-sweep"); s.add_argument("--dataset", default="main"); s.add_argument("--chunk", default="512:64:0"); s.add_argument("--rewrite", action="store_true")
    s.add_argument("--top-k", type=int, nargs="+", default=[10, 20, 30, 50]); s.add_argument("--top-n", type=int, nargs="+", default=[3, 5, 8])
    s.add_argument("--min-score", type=float, nargs="+", default=[0.0, 0.02, 0.05, 0.1, 0.2, 0.3])
    s = sub.add_parser("generate-eval"); s.add_argument("--dataset", default="main"); s.add_argument("--chunk", default="512:64:0"); s.add_argument("--rewrite", action="store_true")
    s.add_argument("--top-k", type=int, default=settings.retrieval_top_k); s.add_argument("--top-n", type=int, default=settings.rerank_top_n)
    s.add_argument("--min-score", type=float, default=settings.rerank_min_score); s.add_argument("--model", default=None); s.add_argument("--limit", type=int, default=0)

    args = p.parse_args()
    handler = {"index": cmd_index, "build-dataset": cmd_build_dataset, "retrieval-sweep": cmd_retrieval_sweep, "generate-eval": cmd_generate_eval}[args.cmd]

    async def runner():
        try:
            await handler(args)
        except BudgetExceeded as exc:
            print(f"\n⛔ {exc}")
        finally:
            await close_qdrant_client()
            print(f"Cost so far: {json.dumps(TRACKER.summary())}")

    asyncio.run(runner())


if __name__ == "__main__":
    main()
