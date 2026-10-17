"""
System Role: Package initialization for reranker providers and factory.
Inputs: N/A
Outputs: Exported BaseRerankerProvider and factory functions.
Ref: ARCHITECTURE.md §5.2 Directory Dictionary
"""

from rerankers.base import BaseRerankerProvider
from rerankers.factory import get_reranker_provider

__all__ = ["BaseRerankerProvider", "get_reranker_provider"]
