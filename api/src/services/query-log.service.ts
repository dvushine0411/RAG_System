/**
 * System Role: Observes the RAG Engine SSE stream as it passes through the gateway and persists one
 *              query_logs record per query (latency, time-to-first-token, token usage, citations, scores).
 * Inputs: Raw SSE text chunks (SseObserver.feed), request context (query, user, endpoint, filter).
 * Outputs: Fire-and-forget QueryLogModel insert — logging failures never break the user's response.
 * Ref: ARCHITECTURE.md §6 Observability, Phase 8 "query latency and token usage monitoring"
 */

import { logger } from "../config/logger.js";
import { QueryLogModel } from "../models/query-log.model.js";
import type { CitationMetadata } from "./rag-engine.client.js";
import { parseSseFrames, type CollectedAnswer, type SseFrame, type TokenUsage } from "./sse-collector.js";

export interface QueryLogContext {
  query: string;
  userId?: string;
  userRole?: string;
  endpoint: "stream" | "json";
  filterDocumentIds?: string[];
}

/** Incrementally parses SSE frames without altering the bytes forwarded to the client. */
export class SseObserver {
  private readonly startedAt = performance.now();
  private buffer = "";
  ttftMs: number | null = null;
  answer = "";
  citations: CitationMetadata[] = [];
  tokenUsage: TokenUsage | null = null;
  errorMessage: string | null = null;

  feed(text: string): void {
    this.buffer += text;
    const { frames, rest } = parseSseFrames(this.buffer);
    this.buffer = rest;
    frames.forEach((f) => this.apply(f));
  }

  finish(): void {
    if (this.buffer.trim()) parseSseFrames(this.buffer + "\n\n").frames.forEach((f) => this.apply(f));
    this.buffer = "";
  }

  elapsedMs(): number {
    return performance.now() - this.startedAt;
  }

  private apply(frame: SseFrame): void {
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(frame.data);
    } catch {
      return;
    }
    if (frame.event === "token") {
      if (this.ttftMs === null) this.ttftMs = this.elapsedMs();
      this.answer += String(payload.delta ?? "");
    } else if (frame.event === "citations") {
      this.citations = (payload.citations as CitationMetadata[]) ?? [];
    } else if (frame.event === "done") {
      this.tokenUsage = (payload.token_usage as TokenUsage) ?? null;
    } else if (frame.event === "error") {
      this.errorMessage = String(payload.message ?? "stream error");
    }
  }
}

interface LogOutcome {
  latencyMs: number;
  ttftMs?: number | null;
  answer: string;
  citations: CitationMetadata[];
  tokenUsage: TokenUsage | null;
  status: "success" | "error" | "aborted";
  errorMessage?: string | null;
}

export function recordQuery(ctx: QueryLogContext, outcome: LogOutcome): void {
  const rerankScores: Record<string, number> = {};
  for (const c of outcome.citations) rerankScores[c.chunk_id] = c.score;

  QueryLogModel.create({
    user_query: ctx.query,
    user_id: ctx.userId,
    user_role: ctx.userRole,
    endpoint: ctx.endpoint,
    status: outcome.status,
    retrieved_chunk_ids: outcome.citations.map((c) => c.chunk_id),
    rerank_scores: rerankScores,
    citations_count: outcome.citations.length,
    generated_response: outcome.answer,
    latency_ms: Math.round(outcome.latencyMs), // validator requires bsonType int
    ttft_ms: outcome.ttftMs != null ? Math.round(outcome.ttftMs) : undefined,
    token_usage: outcome.tokenUsage ?? undefined,
    error_message: outcome.errorMessage ?? undefined,
    filter_document_ids: ctx.filterDocumentIds,
  }).catch((err: unknown) => {
    logger.warn(`[QueryLog] Failed to persist query log: ${err instanceof Error ? err.message : String(err)}`);
  });
}

export function recordCollected(ctx: QueryLogContext, collected: CollectedAnswer, latencyMs: number): void {
  recordQuery(ctx, {
    latencyMs,
    answer: collected.answer,
    citations: collected.citations,
    tokenUsage: collected.token_usage,
    status: "success",
  });
}
