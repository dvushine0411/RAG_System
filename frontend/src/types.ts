/**
 * System Role: Shared TypeScript DTOs mirroring the API Gateway's JSON and SSE contracts.
 * Inputs: none (type declarations only).
 * Outputs: DocumentRecord, Citation, TokenUsage, ChatMessage and request/response shapes.
 */

export type UserRole = "user" | "admin";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  createdAt: string;
}

export interface AuthSessionResponse {
  user: AuthUser;
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
}

export type DocumentStatus = "pending" | "processing" | "completed" | "failed";

export interface DocumentRecord {
  id: string;
  title: string;
  source_type: string;
  file_hash: string;
  total_chunks: number;
  total_tokens: number;
  status: DocumentStatus;
  createdAt: string;
}

export interface UploadResult {
  status: string;
  is_duplicate: boolean;
  message: string;
  document: DocumentRecord;
}

export interface Citation {
  citation_id: number;
  chunk_id: string;
  document_id: string;
  title?: string | null;
  source_type: string;
  page_number?: number | null;
  section_title?: string | null;
  score: number;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface StreamDone {
  finish_reason: string;
  token_usage: TokenUsage;
  latency_ms: number;
  /** Citation ids the answer actually references as [n] (subset of the citations event). */
  used_citation_ids?: number[];
  /** Standalone query used for retrieval when the follow-up was rewritten. */
  retrieval_query?: string | null;
}

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export interface QueryRequest {
  query: string;
  conversation_history?: HistoryMessage[];
  filter?: { document_ids?: string[] };
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  done?: StreamDone;
  error?: string;
  streaming?: boolean;
}
