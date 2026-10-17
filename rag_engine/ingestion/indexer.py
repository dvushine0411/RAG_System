"""
System Role: Reusable end-to-end indexing pipeline — Parse -> Chunk -> (Contextual header) -> Embed -> Upsert.
Inputs: Raw file bytes, filename, document UUID, optional source_type / chunk_size / chunk_overlap overrides.
        Scanned PDF pages are OCR'd via ingestion/pdf_ocr.py before chunking.
Outputs: IndexResult (chunk count, token count, status); points written to settings.qdrant_collection.
Used by: api/routes/ingestion.py (/process) and evaluation/ (indexing eval corpora into eval collections).
"""

import uuid
from dataclasses import dataclass
from typing import List, Optional

from config import settings
from embeddings.factory import get_embedding_provider
from ingestion.chunking import DocumentChunker
from ingestion.contextual_header import build_context_header, with_header
from ingestion.parsers.parser_factory import get_parser
from ingestion.pdf_ocr import ocr_missing_pages
from schemas.embedding import VectorPointDTO
from vectordb.vector_ops import upsert_vectors


@dataclass
class IndexResult:
    total_chunks: int
    total_tokens: int
    status: str  # "completed" | "empty"
    source_type: str


async def index_document(
    file_bytes: bytes,
    filename: str,
    document_id: str,
    source_type: Optional[str] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> IndexResult:
    """Raises ValueError for unsupported formats (mapped to 415 by the route)."""
    resolved_type = (source_type or filename.rsplit(".", 1)[-1]).lower()
    parser = get_parser(filename=filename, source_type=source_type or "")
    sections = parser(file_bytes)
    if resolved_type == "pdf":
        sections = await ocr_missing_pages(file_bytes, sections)  # scanned pages -> OCR (no-op if disabled)
    if not sections:
        return IndexResult(0, 0, "empty", resolved_type)

    chunker = DocumentChunker(
        chunk_size=chunk_size or settings.default_chunk_size,
        chunk_overlap=chunk_overlap or settings.default_chunk_overlap,
    )
    chunks = chunker.chunk_sections(sections=sections, document_id=document_id)
    if not chunks:
        return IndexResult(0, 0, "empty", resolved_type)

    headers = [build_context_header(filename, c.metadata) for c in chunks]
    embeddings = await get_embedding_provider().embed_texts(
        [with_header(h, c.content) for h, c in zip(headers, chunks)]
    )

    points: List[VectorPointDTO] = []
    for chunk, header, vector in zip(chunks, headers, embeddings):
        payload = {
            **chunk.metadata,
            "document_id": document_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "token_count": chunk.token_count,
            "source_type": resolved_type,
            "filename": filename,
        }
        if header:
            payload["context_header"] = header
        points.append(
            VectorPointDTO(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{chunk.chunk_index}")),
                vector=vector,
                payload=payload,
            )
        )

    await upsert_vectors(points)
    return IndexResult(len(points), sum(c.token_count for c in chunks), "completed", resolved_type)
