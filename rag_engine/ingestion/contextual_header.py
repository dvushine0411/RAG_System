"""
System Role: Builds the contextual breadcrumb header ("Document > Section > Page") prepended to a chunk
             before embedding and reranking (optimize_document_chunking Strategy 2).
Inputs: Filename and chunk metadata (section_title, page_number); settings.chunk_context_header_enabled.
Outputs: Header string (or "") and the text actually sent to the embedding / reranker models.
Why: isolated chunks lose their topic ("it uses 512 tokens"); the header restores it for vector search
     and the cross-encoder, while the stored/displayed `content` stays unchanged.
"""

from typing import Any, Mapping, Optional

from config import settings


def build_context_header(filename: Optional[str], metadata: Mapping[str, Any]) -> str:
    if not settings.chunk_context_header_enabled:
        return ""
    parts = []
    if filename:
        parts.append(f"Document: {filename}")
    section = metadata.get("section_title")
    if section:
        parts.append(f"Section: {section}")
    page = metadata.get("page_number")
    if page is not None:
        parts.append(f"Page: {page}")
    return " > ".join(parts)


def with_header(header: Optional[str], content: str) -> str:
    """Text representation used for embedding and reranking."""
    return f"[{header}]\n{content}" if header else content
