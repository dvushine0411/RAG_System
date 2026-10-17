"""
System Role: Centralized settings management loading and validating environment variables, HNSW hyperparameters, retrieval thresholds, and provider selections.
Inputs: Operating system environment variables or .env file parameters.
Outputs: Strongly-typed Settings singleton consumed across rag_engine modules.
Ref: ARCHITECTURE.md §3, §5 Centralized Config Principle
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # MongoDB
    mongo_uri: str = Field(
        default="mongodb://localhost:27017/rag_db",
        description="MongoDB connection string"
    )

    # Qdrant
    qdrant_host: str = Field(default="qdrant")
    qdrant_port: int = Field(default=6333)
    qdrant_grpc_port: int = Field(default=6334)
    qdrant_prefer_grpc: bool = Field(default=True)  # gRPC avoids ~47 ms REST overhead per search (Phase 8 benchmark)
    qdrant_timeout_seconds: int = Field(default=30)
    qdrant_api_key: str = Field(default="")
    qdrant_collection: str = Field(default="document_chunks")

    # Embedding (ARCHITECTURE.md §2.2 Phase A)
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dims: int = Field(default=1536)
    embedding_batch_size: int = Field(default=32)
    embedding_max_retries: int = Field(default=3)

    # Ingestion & Chunking Defaults
    default_chunk_size: int = Field(default=256)  # Phase 8 eval: 256 > 512/800 (Hit@5 .92 vs .82, half the context)
    default_chunk_overlap: int = Field(default=32)
    # Prepend "Document > Section > Page" breadcrumb to chunk text for embedding & reranking (requires re-index)
    chunk_context_header_enabled: bool = Field(default=False)

    # OCR fallback for scanned PDF pages (OpenAI vision) — ingestion/pdf_ocr.py
    pdf_ocr_enabled: bool = Field(default=True)
    pdf_ocr_model: str = Field(default="gpt-4o-mini")
    pdf_ocr_dpi: int = Field(default=150)
    pdf_ocr_concurrency: int = Field(default=6)
    pdf_ocr_max_pages: int = Field(default=300)
    pdf_ocr_min_chars: int = Field(default=50)  # pages with less extracted text are treated as scanned
    pdf_ocr_max_output_tokens: int = Field(default=2500)
    ocr_cache_dir: str = Field(default="/app/.cache/ocr")

    # Query rewriting: condense follow-up questions into standalone queries before retrieval
    query_rewrite_enabled: bool = Field(default=True)  # Phase 8 eval: follow-up Hit .92 -> .96
    query_rewrite_model: str = Field(default="")  # empty -> llm_model
    query_rewrite_max_tokens: int = Field(default=128)
    query_rewrite_history_turns: int = Field(default=6)

    # LLM
    llm_provider: str = Field(default="openai")  # openai | gemini | anthropic | mock
    llm_model: str = Field(default="gpt-4o")
    llm_temperature: float = Field(default=0.0)
    stream_chunk_delay: float = Field(default=0.0)

    # API Keys
    openai_api_key: str = Field(default="")
    cohere_api_key: str = Field(default="")
    google_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")

    # HNSW Search Params (ARCHITECTURE.md §3.1)
    hnsw_m: int = Field(default=16)
    hnsw_ef_construction: int = Field(default=64)
    hnsw_ef_search: int = Field(default=40)
    retrieval_top_k: int = Field(default=50)  # Phase 8 eval: wider pool lets the reranker recover more evidence
    retrieval_min_score: float = Field(default=0.0)

    # Reranker
    reranker_provider: str = Field(default="cohere")  # cohere | onnx_local | mock
    reranker_model: str = Field(default="rerank-english-v3.0")
    rerank_top_n: int = Field(default=3)  # Phase 8 eval: best score with ~40% fewer prompt tokens than 5
    rerank_min_score: float = Field(default=0.0)

    # Evaluation (Phase 8) — rag_engine/evaluation/
    eval_judge_model: str = Field(default="gpt-4o-mini")
    eval_dataset_model: str = Field(default="gpt-4o-mini")
    eval_budget_usd: float = Field(default=3.0)  # hard stop for OpenAI spend per evaluation process
    eval_rerank_min_interval_seconds: float = Field(default=6.5)  # Cohere trial key: 10 rerank calls / minute
    eval_candidate_pool: int = Field(default=50)  # top_k fetched once per question for offline retrieval sweeps
    # USD per 1M tokens (input, output) — used only for the eval budget guard; update if pricing changes
    eval_pricing_per_million: dict = Field(default={
        "gpt-4o-mini": [0.15, 0.60],
        "gpt-4o": [2.50, 10.00],
        "text-embedding-3-small": [0.02, 0.0],
    })

    # System prompt variant (prompting/system_prompt.py): v1 = original, v2 = Phase 8 refusal rules
    system_prompt_version: str = Field(default="v2")

    # Prompt Augmentation & Token Budget (ARCHITECTURE.md Phase 5)
    max_context_tokens: int = Field(default=8192)
    reserved_output_tokens: int = Field(default=1024)


# Singleton instance
settings = Settings()


