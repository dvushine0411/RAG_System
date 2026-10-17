"""
System Role: FastAPI router handling document parsing, chunking, and end-to-end vector indexing pipelines.
Inputs: Multipart file streams, document UUIDs, and optional chunking parameters.
Outputs: ChunkDTO collections or end-to-end IngestProcessResponse confirming Qdrant storage.
Ref: ARCHITECTURE.md §2.2 Phase A & §4.2 Centralized Config Principle
"""

from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
import logging

from config import settings
from ingestion.parsers.parser_factory import get_parser
from ingestion.chunking import DocumentChunker
from schemas.ingestion import IngestResponse
from schemas.vectordb import IngestProcessResponse
from ingestion.indexer import index_document

logger = logging.getLogger("rag_engine.routes.ingestion")

router = APIRouter(prefix="/api/v1/ingest", tags=["Ingestion"])


@router.post(
    "/parse-chunk",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Parse raw document and split into semantic chunks (Phase 2)",
)
async def parse_and_chunk_document(
    file: UploadFile = File(..., description="Multipart file stream forwarded by Node.js API Gateway"),
    document_id: Optional[str] = Form(None, description="UUID assigned to document by Node.js Gateway"),
    source_type: Optional[str] = Form(None, description="Explicit source format (pdf, docx, md, txt, html)"),
    chunk_size: Optional[int] = Form(None, description="Target token count per chunk"),
    chunk_overlap: Optional[int] = Form(None, description="Token overlap between adjacent chunks"),
) -> IngestResponse:
    """
    Parses incoming document stream and decomposes it into semantic ChunkDTOs.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename."
        )

    effective_chunk_size = chunk_size or settings.default_chunk_size
    effective_chunk_overlap = chunk_overlap or settings.default_chunk_overlap

    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Uploaded file '{file.filename}' is empty."
            )

        parser = get_parser(filename=file.filename, source_type=source_type or "")
        sections = parser(file_bytes)
        if not sections:
            return IngestResponse(
                document_id=document_id,
                filename=file.filename,
                source_type=source_type or file.filename.split(".")[-1],
                total_chunks=0,
                total_tokens=0,
                chunks=[],
            )

        chunker = DocumentChunker(chunk_size=effective_chunk_size, chunk_overlap=effective_chunk_overlap)
        chunks = chunker.chunk_sections(sections=sections, document_id=document_id)
        total_tokens = sum(c.token_count for c in chunks)
        detected_ext = file.filename.split(".")[-1].lower() if "." in file.filename else "unknown"

        return IngestResponse(
            document_id=document_id,
            filename=file.filename,
            source_type=(source_type or detected_ext).lower(),
            total_chunks=len(chunks),
            total_tokens=total_tokens,
            chunks=chunks,
        )

    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(val_err))
    except Exception as exc:
        logger.exception(f"Unexpected error parsing '{file.filename}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse document: {str(exc)}"
        )


@router.post(
    "/process",
    response_model=IngestProcessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="End-to-end ingestion: Parse -> Chunk -> Embed -> Upsert into Qdrant (Phase 3)",
)
async def process_document_and_index(
    file: UploadFile = File(..., description="Multipart file stream forwarded by Node.js API Gateway"),
    document_id: str = Form(..., description="UUID assigned to document by Node.js Gateway"),
    source_type: Optional[str] = Form(None, description="Explicit source format (pdf, docx, md, txt, html)"),
    chunk_size: Optional[int] = Form(None, description="Target token count per chunk"),
    chunk_overlap: Optional[int] = Form(None, description="Token overlap between adjacent chunks"),
) -> IngestProcessResponse:
    """
    Executes full ingestion pipeline:
    1. Parse file into structural sections.
    2. Chunk sections using recursive character text splitting.
    3. Generate 1536-dimensional embeddings for all chunks.
    4. Upsert points with payloads directly into Qdrant collection.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename."
        )

    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Uploaded file '{file.filename}' is empty."
            )

        # Parse -> Chunk -> Contextual header -> Embed -> Upsert (shared with evaluation/)
        result = await index_document(
            file_bytes=file_bytes,
            filename=file.filename,
            document_id=document_id,
            source_type=source_type,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        logger.info(
            f"End-to-end ingested '{file.filename}': "
            f"{result.total_chunks} vectors stored in Qdrant collection '{settings.qdrant_collection}'."
        )

        return IngestProcessResponse(
            document_id=document_id,
            filename=file.filename,
            source_type=result.source_type,
            total_chunks=result.total_chunks,
            total_tokens=result.total_tokens,
            collection_name=settings.qdrant_collection,
            status=result.status,
        )

    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(val_err))
    except Exception as exc:
        logger.exception(f"Unexpected error in process pipeline for '{file.filename}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process and index document: {str(exc)}"
        )
