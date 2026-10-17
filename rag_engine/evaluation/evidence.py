"""
System Role: Chunk-config-independent relevance labels — a retrieved chunk is relevant when it contains the
             question's ground-truth evidence quote (token recall >= threshold), so labels survive re-chunking.
Inputs: Evidence quote (verbatim span from the source document) and candidate chunk text.
Outputs: Normalized token lists, evidence recall in [0, 1], boolean relevance.
"""

import re
import unicodedata
from typing import List

RELEVANCE_THRESHOLD = 0.7
_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokens(text: str) -> List[str]:
    return _TOKEN.findall(unicodedata.normalize("NFC", text).lower())


def evidence_recall(evidence: str, chunk_text: str) -> float:
    ev = tokens(evidence)
    if not ev:
        return 0.0
    chunk_vocab = set(tokens(chunk_text))
    return sum(1 for t in ev if t in chunk_vocab) / len(ev)


def is_relevant(evidence: str, chunk_text: str, threshold: float = RELEVANCE_THRESHOLD) -> bool:
    return evidence_recall(evidence, chunk_text) >= threshold


def evidence_in_text(evidence: str, text: str) -> bool:
    """Strict check used when building the dataset: the quote must really come from the chunk."""
    norm = lambda s: " ".join(tokens(s))
    return norm(evidence) in norm(text)
