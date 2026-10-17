"""
System Role: HNSW stress test — measures Qdrant ANN search latency under sustained concurrent load and
             query-time recall vs exact search, on a temporary benchmark collection that mirrors production HNSW settings.
Inputs: CLI args (--points, --qps, --duration, --ef, --top-k); settings.hnsw_m / hnsw_ef_construction / embedding_dims.
Outputs: Console summary + reports/hnsw_stress_<timestamp>.{json,md}; SLA verdict (p95 < 30 ms, p99 < 100 ms @ 50 QPS).
Usage (inside the compose network):
    docker compose run --rm -v ./rag_engine:/app rag_engine python -m benchmarks.stress_hnsw
Ref: .agents/skills/eval_vector_search/SKILL.md §1 (latency SLA) & Strategy 2 (efSearch tuning)
"""

import argparse
import asyncio
import json
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
from qdrant_client.http import models as rest

from config import settings
from vectordb.qdrant_client import close_qdrant_client, get_qdrant_client

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
SLA_P95_MS = 30.0
SLA_P99_MS = 100.0
SLA_QPS = 50


def synthetic_vectors(n: int, dims: int, clusters: int, rng: np.random.Generator) -> np.ndarray:
    """Clustered unit vectors (Gaussian mixture) — closer to real embedding geometry than uniform noise."""
    centers = rng.standard_normal((clusters, dims)).astype(np.float32)
    labels = rng.integers(0, clusters, size=n)
    vecs = centers[labels] + 0.35 * rng.standard_normal((n, dims)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs


def percentile(values: List[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


async def build_collection(name: str, vectors: np.ndarray, batch: int) -> None:
    client = get_qdrant_client()
    await client.create_collection(
        collection_name=name,
        vectors_config=rest.VectorParams(size=vectors.shape[1], distance=rest.Distance.COSINE),
        hnsw_config=rest.HnswConfigDiff(m=settings.hnsw_m, ef_construct=settings.hnsw_ef_construction),
        # Qdrant only builds HNSW once a segment exceeds indexing_threshold (~20 MB by default); below that it
        # brute-forces. Force indexing so the benchmark actually measures the HNSW graph.
        optimizers_config=rest.OptimizersConfigDiff(indexing_threshold=1),
    )
    for start in range(0, len(vectors), batch):
        chunk = vectors[start : start + batch]
        await client.upsert(
            collection_name=name,
            points=rest.Batch(ids=list(range(start, start + len(chunk))), vectors=chunk.tolist()),
            wait=True,
        )
    # Wait until the HNSW graph is fully built before measuring
    for _ in range(600):
        info = await client.get_collection(name)
        if info.status == rest.CollectionStatus.GREEN and (info.indexed_vectors_count or 0) >= len(vectors) * 0.99:
            return
        await asyncio.sleep(0.5)
    raise RuntimeError(f"HNSW index not built after 300s (indexed={info.indexed_vectors_count}/{len(vectors)})")


async def measure_recall(name: str, queries: np.ndarray, top_k: int, ef_values: List[int]) -> Dict[int, Dict[str, float]]:
    client = get_qdrant_client()
    truth = []
    for q in queries:
        exact = await client.search(name, query_vector=q.tolist(), limit=top_k, search_params=rest.SearchParams(exact=True))
        truth.append({p.id for p in exact})

    results: Dict[int, Dict[str, float]] = {}
    for ef in ef_values:
        hits, lat = 0, []
        for q, gt in zip(queries, truth):
            t0 = time.perf_counter()
            ann = await client.search(name, query_vector=q.tolist(), limit=top_k, search_params=rest.SearchParams(hnsw_ef=ef))
            lat.append((time.perf_counter() - t0) * 1000)
            hits += len(gt & {p.id for p in ann})
        results[ef] = {"recall": hits / (len(queries) * top_k), "p50_ms": percentile(lat, 0.5)}
    return results


async def load_level(name: str, queries: np.ndarray, qps: int, duration: float, ef: int, top_k: int) -> Dict[str, float]:
    """Open-loop load: requests are launched on a fixed schedule regardless of response time."""
    client = get_qdrant_client()
    latencies: List[float] = []
    errors = 0
    total = int(qps * duration)
    interval = 1.0 / qps

    async def one(i: int) -> None:
        nonlocal errors
        q = queries[i % len(queries)].tolist()
        t0 = time.perf_counter()
        try:
            await client.search(name, query_vector=q, limit=top_k, search_params=rest.SearchParams(hnsw_ef=ef))
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception:
            errors += 1

    tasks = []
    start = time.perf_counter()
    for i in range(total):
        delay = start + i * interval - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        tasks.append(asyncio.create_task(one(i)))
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    return {
        "target_qps": qps,
        "achieved_qps": round(len(latencies) / elapsed, 1),
        "requests": total,
        "errors": errors,
        "p50_ms": round(percentile(latencies, 0.50), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "p99_ms": round(percentile(latencies, 0.99), 2),
        "max_ms": round(max(latencies), 2) if latencies else float("nan"),
        "mean_ms": round(statistics.fmean(latencies), 2) if latencies else float("nan"),
    }


def write_report(result: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORT_DIR / f"hnsw_stress_{stamp}.json"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        f"# HNSW Stress Test — {stamp}",
        "",
        f"Collection: {result['points']} synthetic clustered vectors, dim={result['dims']}, "
        f"M={result['hnsw_m']}, ef_construct={result['hnsw_ef_construct']}, top_k={result['top_k']}, load ef={result['load_ef']}",
        "",
        "## Recall@K vs exact search",
        "| ef_search | Recall@K | p50 (ms, sequential) |",
        "|---|---|---|",
        *[f"| {ef} | {v['recall']:.4f} | {v['p50_ms']:.2f} |" for ef, v in result["recall"].items()],
        "",
        "## Latency under load (open-loop)",
        "| Target QPS | Achieved | p50 | p95 | p99 | max | errors |",
        "|---|---|---|---|---|---|---|",
        *[
            f"| {r['target_qps']} | {r['achieved_qps']} | {r['p50_ms']} | {r['p95_ms']} | {r['p99_ms']} | {r['max_ms']} | {r['errors']} |"
            for r in result["load"]
        ],
        "",
        f"**SLA (p95 < {SLA_P95_MS} ms, p99 < {SLA_P99_MS} ms @ {SLA_QPS} QPS): {result['sla']}**",
    ]
    md_path = json_path.with_suffix(".md")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--points", type=int, default=10_000)
    parser.add_argument("--clusters", type=int, default=200)
    parser.add_argument("--qps", type=int, nargs="+", default=[25, 50, 100, 200])
    parser.add_argument("--duration", type=float, default=15.0, help="seconds per QPS level")
    parser.add_argument("--ef", type=int, nargs="+", default=[16, 40, 80, 128], help="ef_search values for recall sweep")
    parser.add_argument("--load-ef", type=int, default=settings.hnsw_ef_search, help="ef_search used under load")
    parser.add_argument("--top-k", type=int, default=settings.retrieval_top_k)
    parser.add_argument("--recall-queries", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    dims = settings.embedding_dims
    name = f"bench_hnsw_{uuid.uuid4().hex[:8]}"
    print(f"Building '{name}': {args.points} vectors × {dims} dims (M={settings.hnsw_m}, ef_construct={settings.hnsw_ef_construction})...")

    all_vecs = synthetic_vectors(args.points + 1000, dims, args.clusters, rng)
    corpus, queries = all_vecs[: args.points], all_vecs[args.points :]

    client = get_qdrant_client()
    try:
        t0 = time.perf_counter()
        await build_collection(name, corpus, batch=256)
        print(f"  indexed in {time.perf_counter() - t0:.1f}s")

        recall = await measure_recall(name, queries[: args.recall_queries], args.top_k, args.ef)
        for ef, v in recall.items():
            print(f"  ef_search={ef:<4} Recall@{args.top_k}={v['recall']:.4f}  p50={v['p50_ms']:.2f} ms")

        load = []
        for qps in args.qps:
            r = await load_level(name, queries, qps, args.duration, args.load_ef, args.top_k)
            load.append(r)
            print(f"  {qps:>4} QPS → achieved {r['achieved_qps']}, p50 {r['p50_ms']} ms, p95 {r['p95_ms']} ms, p99 {r['p99_ms']} ms, errors {r['errors']}")

        at_sla = next((r for r in load if r["target_qps"] == SLA_QPS), None)
        sla = "N/A (50 QPS level not run)"
        if at_sla:
            ok = at_sla["p95_ms"] < SLA_P95_MS and at_sla["p99_ms"] < SLA_P99_MS and at_sla["errors"] == 0
            sla = "PASS" if ok else "FAIL"

        result = {
            "points": args.points, "dims": dims, "clusters": args.clusters, "hnsw_m": settings.hnsw_m,
            "hnsw_ef_construct": settings.hnsw_ef_construction, "top_k": args.top_k, "load_ef": args.load_ef,
            "recall": {str(k): v for k, v in recall.items()}, "load": load, "sla": sla,
        }
        report = write_report(result)
        print(f"\nSLA @ {SLA_QPS} QPS: {sla}\nReport: {report}")
    finally:
        await client.delete_collection(name)
        await close_qdrant_client()


if __name__ == "__main__":
    asyncio.run(main())
