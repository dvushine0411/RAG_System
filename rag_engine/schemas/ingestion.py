"""
rag_engine/schemas/ingestion.py
Pydantic schemas for the document parsing and chunking pipeline.
Ref: ARCHITECTURE.md §2.2 Phase A & §4.2
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChunkDTO(BaseModel):
    """Represents an individual text chunk segment produced by chunking."""
    chunk_index: int = Field(..., description="0-based index of chunk in document")
    content: str = Field(..., description="Text content of the chunk segment")
    token_count: int = Field(..., description="Number of tokens in this chunk")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk metadata: page_number, section_title, start_char, end_char, etc."
    )


class IngestResponse(BaseModel):
    """Response returned to Node.js API Gateway after parsing & chunking."""
    document_id: Optional[str] = Field(None, description="UUID assigned by Node.js Gateway")
    filename: str = Field(..., description="Original filename uploaded")
    source_type: str = Field(..., description="Document format: pdf, docx, markdown, text, html")
    total_chunks: int = Field(..., description="Total number of chunks produced")
    total_tokens: int = Field(..., description="Total token count across all chunks")
    chunks: List[ChunkDTO] = Field(..., description="List of generated chunks")
