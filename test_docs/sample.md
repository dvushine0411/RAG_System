# Enterprise RAG Architecture Guide

## 1. Overview
Retrieval-Augmented Generation (RAG) is a pattern for enhancing LLM responses with proprietary organizational data.
By retrieving authoritative context from a knowledge base before generation, RAG eliminates hallucinations and provides grounded citations.

## 2. Ingestion Pipeline
The document ingestion pipeline processes raw multi-format files into semantic vectors.

### 2.1 Parsing
Documents such as PDF, DOCX, Markdown, and HTML are parsed into clean text.
Structural elements like section headers and page numbers are preserved as metadata.

### 2.2 Chunking Strategy
Recursive character splitting breaks large texts into segments of 512 tokens with 64-token overlap.
This ensures boundary integrity while retaining complete semantic context.

| Parameter | Value | Description |
| :--- | :--- | :--- |
| Chunk Size | 512 tokens | Ideal target for embedding models |
| Overlap | 64 tokens | Preserves continuity across boundaries |
| Index | HNSW | Sub-millisecond vector similarity search |

## 3. Deduplication
Node.js API Gateway computes SHA-256 hashes of incoming files.
If a duplicate hash is found in MongoDB, the upload returns an idempotent 200 OK without triggering redundant downstream processing.
