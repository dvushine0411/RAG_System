"""
System Role: Pydantic DTOs for embedding generation, batch requests, and vector point encapsulation.
Inputs: Text strings or chunk lists submitted for vector transformation.
Outputs: Validated embedding vectors (1536-dim) and structured Qdrant point payloads.
Ref: ARCHITECTURE.md §2.2 & §4.2
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    """Request payload containing a list of text segments to be vectorized."""
    texts: List[str] = Field(..., description="List of raw text chunks to embed", min_length=1)
    model: Optional[str] = Field(None, description="Optional override for embedding model name")


class EmbeddingItem(BaseModel):
    """Individual vector embedding representation."""
    index: int = Field(..., description="Original position in input batch")
    embedding: List[float] = Field(..., description="High-dimensional dense float vector")


class EmbeddingResponse(BaseModel):
    """Response containing batch-generated vector embeddings."""
    model: str = Field(..., description="Model name utilized for generation")
    dimension: int = Field(..., description="Embedding vector length (e.g., 1536)")
    total_tokens: int = Field(..., description="Estimated token count across batch")
    embeddings: List[EmbeddingItem] = Field(..., description="Generated embedding vectors")


class VectorPointDTO(BaseModel):
    """Structured point object ready for insertion into Qdrant collection."""
    id: str = Field(..., description="Deterministic or UUID point identifier")
    vector: List[float] = Field(..., description="1536-dim embedding vector")
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk content, document_id, page_number, and hierarchical metadata"
    )
