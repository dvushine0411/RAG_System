"""
System Role: End-to-end integration test verifying the complete Phase 3 ingestion pipeline.
Inputs: Sample Markdown file bytes and synthetic document UUID.
Outputs: Assertions confirming Parse -> Chunk -> Embed -> Qdrant PointStruct assembly.
Ref: ARCHITECTURE.md §2.2 Phase A & §4.2
"""

import asyncio
import io
import os
import sys
import uuid

# Ensure rag_engine root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from starlette.datastructures import Headers
from fastapi import UploadFile
from config import settings
from ingestion.parsers.parser_factory import get_parser
from ingestion.chunking import DocumentChunker
from embeddings.factory import get_embedding_provider
from schemas.embedding import VectorPointDTO


async def run_end_to_end_pipeline_test():
    print("=================================================================")
    print("      PHASE 3 END-TO-END INGESTION -> VECTOR INDEXING TEST       ")
    print("=================================================================\n")

    test_docs_dir = os.path.abspath(os.path.join(parent_dir, "..", "test_docs"))
    md_path = os.path.join(test_docs_dir, "sample.md")
    with open(md_path, "rb") as f:
        file_bytes = f.read()

    doc_id = str(uuid.uuid4())
    print(f"Target Document ID: {doc_id}")

    # 1. Parse
    print("\n[STEP 1] Document Parsing...")
    parser = get_parser("sample.md")
    sections = parser(file_bytes)
    assert len(sections) >= 3
    print(f"  -> Extracted {len(sections)} structural sections.")

    # 2. Chunk
    print("\n[STEP 2] Recursive Character Chunking...")
    chunker = DocumentChunker(chunk_size=128, chunk_overlap=16)
    chunks = chunker.chunk_sections(sections, document_id=doc_id)
    assert len(chunks) >= 3
    print(f"  -> Generated {len(chunks)} chunks with preserved section metadata.")

    # 3. Embed
    print("\n[STEP 3] High-Dimensional Vector Embedding...")
    provider = get_embedding_provider()
    chunk_texts = [c.content for c in chunks]
    vectors = await provider.embed_texts(chunk_texts)
    assert len(vectors) == len(chunks)
    assert len(vectors[0]) == settings.embedding_dims
    print(f"  -> Generated {len(vectors)} embeddings of dimension {settings.embedding_dims}.")

    # 4. PointStruct & Payload Assembly
    print("\n[STEP 4] Assembling Qdrant PointStructs with Payloads...")
    points = []
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        p_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{chunk.chunk_index}"))
        point = VectorPointDTO(
            id=p_id,
            vector=vector,
            payload={
                **chunk.metadata,
                "document_id": doc_id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "token_count": chunk.token_count,
                "source_type": "md",
                "filename": "sample.md",
            },
        )
        points.append(point)

    assert len(points) == len(chunks)
    for p in points:
        assert p.payload["document_id"] == doc_id
        assert "content" in p.payload
        assert len(p.vector) == 1536

    print(f"  -> Successfully packaged {len(points)} Qdrant points with full metadata payload.")
    print("=================================================================")
    print("  [SUCCESS] END-TO-END INGESTION & VECTOR PIPELINE VERIFIED!    ")
    print("=================================================================\n")


if __name__ == "__main__":
    asyncio.run(run_end_to_end_pipeline_test())
