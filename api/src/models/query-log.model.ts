/**
 * System Role: Mongoose model for the query audit log (`query_logs`) used by monitoring and evaluation.
 * Inputs: One record per answered query from query-log.service (latency, TTFT, tokens, citations, scores).
 * Outputs: `query_logs` documents; retention handled by the 90-day TTL index on created_at (db/mongo_init).
 * Note: autoIndex is off — indexes and the $jsonSchema validator are owned by db/mongo_init/001_init_collections.js
 *       (latency_ms must be an int, rerank_scores an object, created_at a date).
 */

import mongoose, { Schema, Document } from "mongoose";

export interface IQueryLog extends Document {
  user_query: string;
  user_id?: string;
  user_role?: string;
  endpoint: "stream" | "json";
  status: "success" | "error" | "aborted";
  retrieved_chunk_ids: string[];
  rerank_scores: Record<string, number>;
  citations_count: number;
  generated_response: string;
  latency_ms: number;
  ttft_ms?: number;
  token_usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  error_message?: string;
  filter_document_ids?: string[];
  created_at: Date;
}

const QueryLogSchema = new Schema<IQueryLog>(
  {
    user_query: { type: String, required: true },
    user_id: { type: String },
    user_role: { type: String },
    endpoint: { type: String, enum: ["stream", "json"], required: true },
    status: { type: String, enum: ["success", "error", "aborted"], required: true },
    retrieved_chunk_ids: { type: [String], default: [] },
    rerank_scores: { type: Schema.Types.Mixed, default: {} },
    citations_count: { type: Number, default: 0 },
    generated_response: { type: String, default: "" },
    latency_ms: { type: Number, required: true },
    ttft_ms: { type: Number },
    token_usage: { type: Schema.Types.Mixed },
    error_message: { type: String },
    filter_document_ids: { type: [String], default: undefined },
    created_at: { type: Date, default: () => new Date() },
  },
  { collection: "query_logs", timestamps: false, autoIndex: false, minimize: false }
);

export const QueryLogModel =
  mongoose.models.QueryLog || mongoose.model<IQueryLog>("QueryLog", QueryLogSchema);
