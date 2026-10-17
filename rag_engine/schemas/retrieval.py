"""
System Role: Pydantic schemas defining retrieval filters, search query requests, scored chunk candidates, and response DTOs.
Inputs: Raw JSON query payloads from API clients or Node.js Gateway.
Outputs: Strongly-typed validation models enforcing search parameters, filters, and scored result structures.
Ref: ARCHITECTURE.md §2.2 Phase B, §4.2, §5.2 Directory Dictionary
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RetrievalFilter(BaseModel):
    """
    Metadata filtering criteria applied directly at Qdrant HNSW vector search level.
    """
    document_ids: Optional[List[str]] = Field(
        default=None,
        description="Filter chunks belonging to one or more document UUIDs"
    )
    source_types: Optional[List[str]] = Field(
        default=None,
        description="Filter chunks by document source format (e.g. ['pdf', 'docx'])"
    )
    created_after: Optional[str] = Field(
        default=None,
        description="ISO-8601 timestamp string for chunks created on or after this date"
    )
    created_before: Optional[str] = Field(
        default=None,
        description="ISO-8601 timestamp string for chunks created on or before this date"
    )
    metadata_match: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary key-value equality conditions matched against chunk payload"
    )


class RetrievalQueryRequest(BaseModel):
    """
    Payload for executing vector similarity search and reranking on the corpus.
    """
    query: str = Field(
        ...,
        min_length=1,
        description="Raw natural language search query string"
    )
    filter: Optional[RetrievalFilter] = Field(
        default=None,
        description="Optional metadata filtering constraints"
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Number of candidate vector chunks retrieved from Qdrant HNSW (defaults to settings.retrieval_top_k)"
    )
    ef_search: Optional[int] = Field(
        default=None,
        ge=1,
        le=512,
        description="HNSW exploration depth efSearch parameter (defaults to settings.hnsw_ef_search)"
    )
    top_n: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description="Final number of top reranked chunks returned (defaults to settings.rerank_top_n)"
    )
    score_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum vector similarity / rerank score cutoff"
    )
    rerank_min_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum reranker relevance score kept after stage 2 (defaults to settings.rerank_min_score)"
    )
    rerank: bool = Field(
        default=True,
        description="Whether to execute second-stage cross-encoder / reranking model"
    )


class ScoredChunkDTO(BaseModel):
    """
    Scored chunk representation containing content, provenance metadata, and ranking scores.
    """
    id: str = Field(..., description="Qdrant point UUID")
    document_id: str = Field(..., description="Parent document UUID")
    chunk_index: int = Field(..., description="Positional index within document")
    content: str = Field(..., description="Chunk text content")
    token_count: int = Field(..., description="Estimated token count of the chunk")
    source_type: str = Field(..., description="Document format ('pdf', 'docx', etc.)")
    page_number: Optional[int] = Field(default=None, description="Page number if applicable")
    section_title: Optional[str] = Field(default=None, description="Section heading if applicable")
    vector_score: float = Field(..., description="First-stage HNSW vector similarity score")
    rerank_score: Optional[float] = Field(default=None, description="Second-stage reranker relevance score")
    final_score: float = Field(..., description="Final calibrated score used for ordering")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional chunk payload fields")


class RetrievalResponse(BaseModel):
    """
    Standardized response returned by the retrieval pipeline.
    """
    query: str = Field(..., description="Input query string")
    total_candidates: int = Field(..., description="Number of candidates retrieved from HNSW")
    returned_count: int = Field(..., description="Number of chunks returned after reranking and filtering")
    fallback_used: bool = Field(default=False, description="Flag indicating if vector ranking fallback was used")
    status: str = Field(default="success", description="Status code ('success', 'no_match', 'error')")
    message: Optional[str] = Field(default=None, description="Diagnostic or fallback message")
    results: List[ScoredChunkDTO] = Field(default_factory=list, description="Ranked list of top-N chunks")
