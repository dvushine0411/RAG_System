"""
System Role: Candidate pool cache — for each (collection, retrieval query) fetch the top `eval_candidate_pool`
             chunks by vector similarity ONCE, rerank ALL of them ONCE (rate-limited Cohere), and cache to disk.
             Any (top_k, top_n, rerank_min_score) configuration is then simulated offline at zero API cost.
Inputs: Retrieval query text, eval collection (via corpus.use_config), production embedding + reranker providers.
Outputs: List[ScoredChunkDTO] per simulated config; cache files evaluation/cache/<collection>.json.
Why valid: cross-encoder relevance depends only on the (query, chunk) pair, not on the other candidates.
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from config import settings
from embeddings.factory import get_embedding_provider
from evaluation.cost_tracker import TRACKER
from ingestion.chunking import count_tokens
from rerankers.factory import get_reranker_provider
from retrieval.retriever import VectorRetriever
from schemas.retrieval import RetrievalQueryRequest, ScoredChunkDTO

CACHE_DIR = Path(__file__).resolve().parent / "cache"


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int
    top_n: int
    min_score: float

    def label(self) -> str:
        return f"k{self.top_k}_n{self.top_n}_s{self.min_score:g}"


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self.min_interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


class CandidateCache:
    def __init__(self, collection: str) -> None:
        self.collection = collection
        self.path = CACHE_DIR / f"{collection}.json"
        self.data: Dict[str, List[dict]] = json.loads(self.path.read_text("utf-8")) if self.path.exists() else {}
        self.retriever = VectorRetriever()
        self.limiter = RateLimiter(settings.eval_rerank_min_interval_seconds)
        self.rerank_provider_name = type(get_reranker_provider()).__name__

    def _key(self, query: str) -> str:
        return hashlib.sha1(f"{self.rerank_provider_name}|{settings.embedding_model}|{query}".encode()).hexdigest()

    def save(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    async def pool(self, query: str) -> List[ScoredChunkDTO]:
        key = self._key(query)
        if key not in self.data:
            # Stage 1 only (no rerank) through the production retriever, with the full pool size
            res = await self.retriever.retrieve_and_rerank(
                RetrievalQueryRequest(query=query, top_k=settings.eval_candidate_pool, top_n=settings.eval_candidate_pool,
                                      rerank=False, rerank_min_score=0.0)
            )
            TRACKER.add(settings.embedding_model, count_tokens(query), 0)
            candidates = res.results
            if candidates:
                reranked = None
                for attempt in range(5):
                    await self.limiter.wait()
                    try:
                        reranked = await get_reranker_provider().rerank(query=query, chunks=candidates, top_n=len(candidates))
                        break
                    except Exception as exc:  # Cohere trial: 429 counts a sliding 60 s window (incl. retries)
                        if "429" not in str(exc) or attempt == 4:
                            raise
                        print(f"\n  Cohere 429 — waiting 61 s (attempt {attempt + 1}/5)", flush=True)
                        await asyncio.sleep(61)
                TRACKER.cohere_calls += 1
                scores = {c.id: c.rerank_score for c in reranked}
                candidates = [c.model_copy(update={"rerank_score": scores.get(c.id)}) for c in candidates]
            self.data[key] = [c.model_dump() for c in candidates]
            self.save()
        return [ScoredChunkDTO(**c) for c in self.data[key]]

    @staticmethod
    def simulate(pool: List[ScoredChunkDTO], cfg: RetrievalConfig) -> List[ScoredChunkDTO]:
        """Same semantics as VectorRetriever: vector top_k -> rerank order -> min score -> top_n."""
        stage1 = sorted(pool, key=lambda c: c.vector_score, reverse=True)[: cfg.top_k]
        ranked = sorted(stage1, key=lambda c: (c.rerank_score if c.rerank_score is not None else c.vector_score), reverse=True)
        out = []
        for c in ranked:
            score = c.rerank_score if c.rerank_score is not None else c.vector_score
            if cfg.min_score > 0 and score < cfg.min_score:
                continue
            out.append(c.model_copy(update={"final_score": score}))
        return out[: cfg.top_n]


def relevance_flags(chunks: List[ScoredChunkDTO], evidence: Optional[str]) -> List[bool]:
    from evaluation.evidence import is_relevant

    return [bool(evidence) and is_relevant(evidence, c.content) for c in chunks]
