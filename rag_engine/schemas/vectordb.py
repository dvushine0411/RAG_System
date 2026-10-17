"""
System Role: Pydantic DTOs for Vector Database (Qdrant) operations, collection schemas, and lifecycle metrics.
Inputs: Vector point lists for upsert, document UUIDs for deletion, and collection status queries.
Outputs: Validated execution responses (upsert counts, delete confirmations, collection metadata).
Ref: ARCHITECTURE.md §3 & §4.2
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from schemas.embedding import VectorPointDTO


class VectorUpsertRequest(BaseModel):
    """Payload for batch vector upsert into Qdrant."""
    points: List[VectorPointDTO] = Field(..., description="List of points with vectors and payloads", min_length=1)


class VectorUpsertResponse(BaseModel):
    """Result of vector upsert operation."""
    collection_name: str = Field(..., description="Target Qdrant collection name")
    upserted_count: int = Field(..., description="Number of vector points stored")
    status: str = Field(..., description="Operation status ('completed' or 'failed')")


class VectorDeleteResponse(BaseModel):
    """Result of deleting vector points by document filter."""
    collection_name: str = Field(..., description="Target Qdrant collection name")
    document_id: str = Field(..., description="Document identifier whose chunks were deleted")
    status: str = Field(..., description="Operation status ('completed')")


class CollectionInfoDTO(BaseModel):
    """Metadata describing the Qdrant collection and HNSW index configuration."""
    name: str = Field(..., description="Collection name")
    status: str = Field(..., description="Collection operational status ('green', 'yellow', etc.)")
    vectors_count: int = Field(..., description="Total points currently indexed in collection")
    dimension: int = Field(..., description="Vector dimensionality (1536)")
    distance: str = Field(..., description="Distance metric ('Cosine')")
    hnsw_m: int = Field(..., description="HNSW graph M parameter")
    hnsw_ef_construct: int = Field(..., description="HNSW build ef_construction parameter")


class IngestProcessResponse(BaseModel):
    """End-to-end response after Parsing, Chunking, Embedding, and Qdrant Indexing."""
    document_id: str = Field(..., description="Document identifier UUID")
    filename: str = Field(..., description="Uploaded file name")
    source_type: str = Field(..., description="Parsed file format (pdf, docx, md, txt, html)")
    total_chunks: int = Field(..., description="Number of chunks created and indexed")
    total_tokens: int = Field(..., description="Cumulative token count across all chunks")
    collection_name: str = Field(..., description="Vector collection where points reside")
    status: str = Field(default="completed", description="Lifecycle status")
