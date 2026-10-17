/**
 * api/src/routes/query.route.ts
 * Fastify routes exposing the end-to-end RAG query endpoints:
 *  - POST /api/v1/query/stream : pipes Server-Sent Events (SSE) from RAG Engine to the client.
 *  - POST /api/v1/query        : consumes the same SSE stream and returns a single JSON answer.
 * Inputs: JSON body validated by QueryRequestSchema (query, conversation_history, filter, overrides).
 * Outputs: text/event-stream frames (citations -> token* -> done) or CollectedAnswer JSON.
 * Ref: ARCHITECTURE.md §2.2 Phase B step 1-7, Phase 6-7
 * Auth: both endpoints require a valid Bearer access token (requireAuth).
 * Monitoring: every query is persisted to query_logs (latency, TTFT, tokens, citations) via query-log.service.
 */

import { FastifyInstance, FastifyPluginAsync, FastifyRequest } from "fastify";
import { z } from "zod";
import { Readable } from "node:stream";
import { ragEngineClient } from "../services/rag-engine.client.js";
import { collectSseAnswer } from "../services/sse-collector.js";
import { QueryLogContext, recordCollected, recordQuery, SseObserver } from "../services/query-log.service.js";
import { requireAuth } from "../middlewares/auth.middleware.js";

const ChatMessageSchema = z.object({
  role: z.enum(["system", "user", "assistant"]),
  content: z.string().min(1, "Message content must not be empty"),
});

export const QueryRequestSchema = z.object({
  query: z.string().min(1, "Query string is required"),
  conversation_history: z.array(ChatMessageSchema).optional(),
  filter: z
    .object({
      document_ids: z.array(z.string()).optional(),
      source_types: z.array(z.string()).optional(),
      created_after: z.string().optional(),
      created_before: z.string().optional(),
      metadata_match: z.record(z.unknown()).optional(),
    })
    .optional(),
  retrieval_top_k: z.number().int().positive().optional(),
  rerank_top_n: z.number().int().positive().optional(),
  temperature: z.number().min(0).max(2).optional(),
  max_tokens: z.number().int().positive().optional(),
  model: z.string().optional(),
  metadata: z.record(z.unknown()).optional(),
});

function logContext(request: FastifyRequest, data: z.infer<typeof QueryRequestSchema>, endpoint: "stream" | "json"): QueryLogContext {
  return {
    query: data.query,
    userId: request.user?.sub,
    userRole: request.user?.role,
    endpoint,
    filterDocumentIds: data.filter?.document_ids,
  };
}

export const queryRoute: FastifyPluginAsync = async (fastify: FastifyInstance) => {
  fastify.post("/api/v1/query/stream", { preHandler: requireAuth }, async (request, reply) => {
    const parseResult = QueryRequestSchema.safeParse(request.body);

    if (!parseResult.success) {
      return reply.status(400).send({
        error: "Validation failed",
        details: parseResult.error.flatten(),
      });
    }

    const ctx = logContext(request, parseResult.data, "stream");
    const observer = new SseObserver();

    try {
      const upstreamRes = await ragEngineClient.streamQuery(parseResult.data);

      if (!upstreamRes.body) {
        throw new Error("No response body received from RAG Engine stream");
      }

      // Set Server-Sent Events headers
      reply.raw.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      });

      // Stream upstream chunks directly to client
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const nodeStream = Readable.fromWeb(upstreamRes.body as any);
      nodeStream.pipe(reply.raw);

      // Observe frames for monitoring without touching the bytes sent to the client
      const decoder = new TextDecoder();
      let logged = false;
      const finalize = (status: "success" | "error" | "aborted") => {
        if (logged) return;
        logged = true;
        observer.finish();
        recordQuery(ctx, {
          latencyMs: observer.elapsedMs(),
          ttftMs: observer.ttftMs,
          answer: observer.answer,
          citations: observer.citations,
          tokenUsage: observer.tokenUsage,
          status: observer.errorMessage ? "error" : status,
          errorMessage: observer.errorMessage,
        });
      };
      nodeStream.on("data", (chunk: Buffer) => observer.feed(decoder.decode(chunk, { stream: true })));
      nodeStream.on("end", () => finalize("success"));
      nodeStream.on("error", () => finalize("error"));

      // Clean up upstream connection if client disconnects early
      request.raw.on("close", () => {
        if (!nodeStream.readableEnded) finalize("aborted");
        nodeStream.destroy();
      });
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      request.log.error(err, "Failed to stream query response");
      recordQuery(ctx, { latencyMs: observer.elapsedMs(), answer: "", citations: [], tokenUsage: null, status: "error", errorMessage });

      if (!reply.raw.headersSent) {
        return reply.status(502).send({
          error: "Failed to stream response from RAG Engine",
          message: errorMessage,
        });
      }
      reply.raw.end();
    }
  });

  fastify.post("/api/v1/query", { preHandler: requireAuth }, async (request, reply) => {
    const parseResult = QueryRequestSchema.safeParse(request.body);

    if (!parseResult.success) {
      return reply.status(400).send({
        error: "Validation failed",
        details: parseResult.error.flatten(),
      });
    }

    const ctx = logContext(request, parseResult.data, "json");
    const startedAt = performance.now();

    try {
      const upstreamRes = await ragEngineClient.streamQuery(parseResult.data);

      if (!upstreamRes.body) {
        throw new Error("No response body received from RAG Engine stream");
      }

      const collected = await collectSseAnswer(upstreamRes.body);
      recordCollected(ctx, collected, performance.now() - startedAt);
      return reply.status(200).send({ query: parseResult.data.query, ...collected });
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      request.log.error(err, "Failed to collect query response");
      recordQuery(ctx, { latencyMs: performance.now() - startedAt, answer: "", citations: [], tokenUsage: null, status: "error", errorMessage });
      return reply.status(502).send({
        error: "Failed to get response from RAG Engine",
        message: errorMessage,
      });
    }
  });
};
