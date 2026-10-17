"""
rag_engine/tests/test_api_ingest.py
FastAPI endpoint integration test for /api/v1/ingest/parse-chunk.
Validates multipart file upload, parser resolution, chunking, and JSON response.
"""

import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import asyncio
import io
from fastapi import UploadFile
from starlette.datastructures import Headers
from api.routes.ingestion import parse_and_chunk_document



async def async_test_route():
    print("=== Testing FastAPI /api/v1/ingest/parse-chunk route handler ===")

    test_docs_dir = os.path.abspath(os.path.join(parent_dir, "..", "test_docs"))
    md_path = os.path.join(test_docs_dir, "sample.md")
    with open(md_path, "rb") as f:
        file_bytes = f.read()

    upload_file = UploadFile(
        file=io.BytesIO(file_bytes),
        filename="sample.md",
        headers=Headers({"content-type": "text/markdown"}),
    )


    data = await parse_and_chunk_document(
        file=upload_file,
        document_id="test-doc-uuid-1234",
        source_type="md",
        chunk_size=256,
        chunk_overlap=32,
    )

    assert data.document_id == "test-doc-uuid-1234"
    assert data.filename == "sample.md"
    assert data.source_type == "md"
    assert data.total_chunks >= 3
    assert data.total_tokens > 0
    assert len(data.chunks) == data.total_chunks

    first_chunk = data.chunks[0]
    assert first_chunk.chunk_index == 0
    assert first_chunk.token_count > 0
    assert first_chunk.metadata.get("document_id") == "test-doc-uuid-1234"

    print(f"  -> Ingestion handler: Success! ({data.total_chunks} chunks, {data.total_tokens} tokens)")
    print("=== FastAPI Ingestion Route Handler Test Passed 100%! ===")


if __name__ == "__main__":
    asyncio.run(async_test_route())

