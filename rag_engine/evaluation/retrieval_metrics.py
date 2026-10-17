"""
System Role: Retrieval quality metrics over binary relevance labels (one evidence per question).
Inputs: Ordered list of booleans (is each returned chunk relevant?) per question.
Outputs: Hit@k (= Recall@k with a single evidence), reciprocal rank, nDCG@k; aggregation helpers.
"""

import math
from statistics import fmean
from typing import Dict, List, Sequence


def hit_at(rel: Sequence[bool], k: int) -> float:
    return 1.0 if any(rel[:k]) else 0.0


def reciprocal_rank(rel: Sequence[bool]) -> float:
    for i, r in enumerate(rel, start=1):
        if r:
            return 1.0 / i
    return 0.0


def ndcg_at(rel: Sequence[bool], k: int) -> float:
    """Binary nDCG; the ideal ranking puts every relevant returned chunk first (the evidence can span
    two overlapping chunks, so the ideal DCG is not always 1)."""
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(rel[:k]) if r)
    n_rel = min(sum(1 for r in rel[:k] if r), k)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
    return dcg / ideal if ideal else 0.0


def aggregate(per_question: List[Dict[str, float]]) -> Dict[str, float]:
    if not per_question:
        return {}
    keys = per_question[0].keys()
    return {k: round(fmean(q[k] for q in per_question), 4) for k in keys}
