"""
System Role: Context Assembler generating structured <context> XML blocks with numbered citation tags and metadata provenance catalogs.
Inputs: List of ScoredChunkDTO objects.
Outputs: Formatted context block string and corresponding CitationMetadata list.
Ref: ARCHITECTURE.md §2.2 Phase B step 5, §5.2 Directory Dictionary
"""

from typing import List, Tuple
from schemas.retrieval import ScoredChunkDTO
from schemas.augmentation import CitationMetadata


def assemble_context(
    chunks: List[ScoredChunkDTO],
) -> Tuple[str, List[CitationMetadata]]:
    """
    Formats candidate chunks into a structured XML-tagged context block with sequential [1], [2] markers.

    Args:
        chunks: List of ScoredChunkDTO objects ordered by relevance.

    Returns:
        Tuple containing:
            - Formatted context string enclosed in <context> tags.
            - List of CitationMetadata mapping each [i] marker back to its source chunk.
    """
    if not chunks:
        empty_context = "<context>\n(No relevant documents retrieved.)\n</context>"
        return empty_context, []

    formatted_segments: List[str] = []
    citations: List[CitationMetadata] = []

    for idx, chunk in enumerate(chunks, start=1):
        # Extract metadata provenance details
        metadata = chunk.metadata or {}
        doc_title = str(
            metadata.get("title")
            or metadata.get("original_filename")
            or metadata.get("filename")
            or f"Doc-{chunk.document_id[:8]}"
        )
        source_type = str(chunk.source_type or metadata.get("source_type") or "unknown")
        section = chunk.section_title or metadata.get("section_title")
        page = chunk.page_number or metadata.get("page_number")

        meta_parts: List[str] = [f"Source: {doc_title}"]
        if section:
            meta_parts.append(f"Section: {section}")
        if page is not None:
            meta_parts.append(f"Page: {page}")
        meta_parts.append(f"Format: {source_type}")
        meta_parts.append(f"Relevance: {chunk.final_score:.2f}")

        meta_header = " | ".join(meta_parts)

        # Assemble segment with citation tag [i]
        segment_text = f"[{idx}] {meta_header}\n{chunk.content.strip()}"
        formatted_segments.append(segment_text)

        # Record citation entry
        citation_entry = CitationMetadata(
            citation_id=idx,
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            title=doc_title,
            source_type=source_type,
            page_number=int(page) if page is not None else None,
            section_title=str(section) if section else None,
            score=round(chunk.final_score, 4),
        )
        citations.append(citation_entry)

    joined_content = "\n\n".join(formatted_segments)
    full_context_block = f"<context>\n{joined_content}\n</context>"

    return full_context_block, citations
