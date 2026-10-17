/**
 * System Role: HTTP Client forwarding file streams, ingestion requests, and vector operations to Python RAG Engine.
 * Inputs: Document binary buffers, document UUIDs, and chunking hyperparameters.
 * Outputs: IngestResponse, IngestProcessResponse, and VectorDeleteResponse JSON objects.
 * Ref: ARCHITECTURE.md §2.2 & §5 Centralized Config Principle
 */

import { envConfig } from "../config/env.config.js";
import { logger } from "../config/logger.js";

export interface ChunkDTO {
  chunk_index: number;
  content: string;
  token_count: number;
  metadata: Record<string, unknown>;
}

export interface IngestResponse {
  document_id?: string;
  filename: string;
  source_type: string;
  total_chunks: number;
  total_tokens: number;
  chunks: ChunkDTO[];
}

export interface IngestProcessResponse {
  document_id: string;
  filename: string;
  source_type: string;
  total_chunks: number;
  total_tokens: number;
  collection_name: string;
  status: string;
}

export interface VectorDeleteResponse {
  collection_name: string;
  document_id: string;
  status: string;
}

export interface ParseChunkOptions {
  documentId?: string;
  sourceType?: string;
  chunkSize?: number;
  chunkOverlap?: number;
}

export class RagEngineClient {
  private baseUrl: string;

  constructor(baseUrl: string = envConfig.RAG_ENGINE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  /**
   * Forwards file buffer as multipart/form-data to Python RAG Engine's /api/v1/ingest/parse-chunk (Phase 2).
   */
  public async parseAndChunk(
    fileBuffer: Buffer,
    filename: string,
    options: ParseChunkOptions = {}
  ): Promise<IngestResponse> {
    const url = `${this.baseUrl}/api/v1/ingest/parse-chunk`;
    const formData = new FormData();

    const blob = new Blob([fileBuffer]);
    formData.append("file", blob, filename);

    if (options.documentId) formData.append("document_id", options.documentId);
    if (options.sourceType) formData.append("source_type", options.sourceType);
    if (options.chunkSize) formData.append("chunk_size", String(options.chunkSize));
    if (options.chunkOverlap) formData.append("chunk_overlap", String(options.chunkOverlap));

    logger.info(`[RagEngineClient] Forwarding '${filename}' to ${url}`);

    const res = await fetch(url, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const errText = await res.text();
      logger.error(`[RagEngineClient] Response error ${res.status}: ${errText}`);
      throw new Error(`RAG Engine error (${res.status}): ${errText}`);
    }

    const data = (await res.json()) as IngestResponse;
    logger.info(
      `[RagEngineClient] Received ${data.total_chunks} chunks (${data.total_tokens} tokens) for '${filename}'`
    );
    return data;
  }

  /**
   * Executes end-to-end ingestion: Parse -> Chunk -> Embed -> Qdrant Index (Phase 3).
   */
  public async processAndIndex(
    fileBuffer: Buffer,
    filename: string,
    documentId: string,
    options: { sourceType?: string; chunkSize?: number; chunkOverlap?: number } = {}
  ): Promise<IngestProcessResponse> {
    const url = `${this.baseUrl}/api/v1/ingest/process`;
    const formData = new FormData();

    const blob = new Blob([fileBuffer]);
    formData.append("file", blob, filename);
    formData.append("document_id", documentId);

    if (options.sourceType) formData.append("source_type", options.sourceType);
    if (options.chunkSize) formData.append("chunk_size", String(options.chunkSize));
    if (options.chunkOverlap) formData.append("chunk_overlap", String(options.chunkOverlap));

    logger.info(`[RagEngineClient] Forwarding '${filename}' (id: ${documentId}) to ${url}`);

    const res = await fetch(url, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const errText = await res.text();
      logger.error(`[RagEngineClient] Ingest/process error ${res.status}: ${errText}`);
      throw new Error(`RAG Engine process error (${res.status}): ${errText}`);
    }

    const data = (await res.json()) as IngestProcessResponse;
    logger.info(
      `[RagEngineClient] Processed & indexed '${filename}': ${data.total_chunks} vectors in Qdrant '${data.collection_name}'.`
    );
    return data;
  }

  /**
   * Deletes all vector points for a given document from Qdrant collection.
   */
  public async deleteVectors(documentId: string): Promise<VectorDeleteResponse> {
    const url = `${this.baseUrl}/api/v1/vectors/document/${documentId}`;
    logger.info(`[RagEngineClient] Requesting vector deletion for doc ${documentId}`);

    const res = await fetch(url, { method: "DELETE" });
    if (!res.ok) {
      const errText = await res.text();
      logger.error(`[RagEngineClient] Vector deletion error ${res.status}: ${errText}`);
      throw new Error(`RAG Engine vector delete error (${res.status}): ${errText}`);
    }

    return (await res.json()) as VectorDeleteResponse;
  }

  /**
   * Forwards retrieval query with HNSW and Reranking options to Python RAG Engine (Phase 4).
   */
  public async retrieveAndRerank(options: RetrievalQueryOptions): Promise<RetrievalResponse> {
    const url = `${this.baseUrl}/api/v1/retrieval/search`;
    logger.info(`[RagEngineClient] Forwarding search query '${options.query.substring(0, 40)}...' to ${url}`);

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    });

    if (!res.ok) {
      const errText = await res.text();
      logger.error(`[RagEngineClient] Retrieval error ${res.status}: ${errText}`);
      throw new Error(`RAG Engine retrieval error (${res.status}): ${errText}`);
    }

    const data = (await res.json()) as RetrievalResponse;
    logger.info(
      `[RagEngineClient] Retrieved ${data.returned_count} chunks (fallback=${data.fallback_used}, status=${data.status})`
    );
    return data;
  }

  /**
   * Forwards retrieved chunks and query to Python RAG Engine for prompt augmentation (Phase 5).
   */
  public async assemblePrompt(options: AugmentationOptions): Promise<AugmentedPromptResponse> {
    const url = `${this.baseUrl}/api/v1/augmentation/assemble`;
    logger.info(`[RagEngineClient] Assembling prompt for query '${options.query.substring(0, 40)}...' at ${url}`);

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    });

    if (!res.ok) {
      const errText = await res.text();
      logger.error(`[RagEngineClient] Augmentation error ${res.status}: ${errText}`);
      throw new Error(`RAG Engine augmentation error (${res.status}): ${errText}`);
    }

    const data = (await res.json()) as AugmentedPromptResponse;
    logger.info(
      `[RagEngineClient] Assembled prompt with ${data.assembled_messages.length} messages, ` +
        `${data.citations.length} citations (Tokens: ${data.budget_report.total_prompt_tokens}).`
    );
    return data;
  }

  /**
   * Executes end-to-end RAG query and returns a readable stream response of Server-Sent Events (Phase 6).
   */
  public async streamQuery(payload: QueryStreamPayload): Promise<Response> {
    const url = `${this.baseUrl}/api/v1/query/stream`;
    logger.info(`[RagEngineClient] Forwarding query stream to ${url} for: '${payload.query.slice(0, 50)}...'`);

    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errText = await res.text();
      logger.error(`[RagEngineClient] Query stream error ${res.status}: ${errText}`);
      throw new Error(`RAG Engine stream error (${res.status}): ${errText}`);
    }

    return res;
  }
}

export interface QueryStreamPayload {
  query: string;
  conversation_history?: ChatMessageDTO[];
  filter?: RetrievalFilter;
  retrieval_top_k?: number;
  rerank_top_n?: number;
  temperature?: number;
  max_tokens?: number;
  model?: string;
  metadata?: Record<string, unknown>;
}

export interface ChatMessageDTO {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface CitationMetadata {
  citation_id: number;
  chunk_id: string;
  document_id: string;
  title?: string | null;
  source_type: string;
  page_number?: number | null;
  section_title?: string | null;
  score: number;
}

export interface TokenBudgetReport {
  system_tokens: number;
  query_tokens: number;
  history_tokens: number;
  context_tokens: number;
  total_prompt_tokens: number;
  max_context_tokens: number;
  reserved_output_tokens: number;
  chunks_included: number;
  chunks_truncated: number;
}

export interface AugmentationOptions {
  query: string;
  chunks: ScoredChunkDTO[];
  conversation_history?: ChatMessageDTO[];
  custom_system_role?: string;
  max_context_tokens?: number;
  reserved_output_tokens?: number;
}

export interface AugmentedPromptResponse {
  query: string;
  system_prompt: string;
  context_block: string;
  assembled_messages: ChatMessageDTO[];
  citations: CitationMetadata[];
  budget_report: TokenBudgetReport;
}

export interface RetrievalFilter {
  document_ids?: string[];
  source_types?: string[];
  created_after?: string;
  created_before?: string;
  metadata_match?: Record<string, unknown>;
}

export interface RetrievalQueryOptions {
  query: string;
  filter?: RetrievalFilter;
  top_k?: number;
  ef_search?: number;
  top_n?: number;
  score_threshold?: number;
  rerank?: boolean;
}

export interface ScoredChunkDTO {
  id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  token_count: number;
  source_type: string;
  page_number?: number | null;
  section_title?: string | null;
  vector_score: number;
  rerank_score?: number | null;
  final_score: number;
  metadata: Record<string, unknown>;
}

export interface RetrievalResponse {
  query: string;
  total_candidates: number;
  returned_count: number;
  fallback_used: boolean;
  status: string;
  message?: string | null;
  results: ScoredChunkDTO[];
}

export const ragEngineClient = new RagEngineClient();


