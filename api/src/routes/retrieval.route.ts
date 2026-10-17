/**
 * System Role: Fastify route handlers exposing retrieval and reranking search endpoints with Zod schema validation.
 * Inputs: JSON HTTP POST payloads conforming to RetrievalQuerySchema.
 * Outputs: Scored candidate chunks retrieved from Qdrant and ranked by Cross-Encoder.
 * Ref: ARCHITECTURE.md §2.2 Phase B, §5 Centralized Config Principle
 * Auth: requires a valid Bearer access token (requireAuth).
 */

import { FastifyInstance, FastifyPluginAsync } from "fastify";
import { z } from "zod";
import { ragEngineClient } from "../services/rag-engine.client.js";
import { logger } from "../config/logger.js";
import { requireAuth } from "../middlewares/auth.middleware.js";

const RetrievalFilterSchema = z
  .object({
    document_ids: z.array(z.string().uuid().or(z.string())).optional(),
    source_types: z.array(z.string()).optional(),
    created_after: z.string().datetime().or(z.string()).optional(),
    created_before: z.string().datetime().or(z.string()).optional(),
    metadata_match: z.record(z.unknown()).optional(),
  })
  .optional();

const RetrievalQuerySchema = z.object({
  query: z.string().min(1, "Query string cannot be empty"),
  filter: RetrievalFilterSchema,
  top_k: z.number().int().min(1).max(100).optional(),
  ef_search: z.number().int().min(1).max(512).optional(),
  top_n: z.number().int().min(1).max(50).optional(),
  score_threshold: z.number().min(0).max(1).optional(),
  rerank: z.boolean().optional().default(true),
});

export const retrievalRoute: FastifyPluginAsync = async (server: FastifyInstance) => {
  /**
   * POST /api/v1/retrieval/search
   * Executes HNSW vector similarity search and Cross-Encoder reranking.
   */
  server.post("/search", { preHandler: requireAuth }, async (req, reply) => {
    const parseResult = RetrievalQuerySchema.safeParse(req.body);
    if (!parseResult.success) {
      return reply.status(400).send({
        error: "Bad Request",
        message: "Invalid retrieval query payload",
        details: parseResult.error.format(),
      });
    }

    const payload = parseResult.data;
    logger.info(`[RetrievalRoute] Processing search query: '${payload.query.substring(0, 50)}...'`);

    try {
      const response = await ragEngineClient.retrieveAndRerank(payload);
      return reply.status(200).send(response);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : String(err);
      logger.error(`[RetrievalRoute] Retrieval request failed: ${errMsg}`);
      return reply.status(502).send({
        error: "Bad Gateway",
        message: `RAG retrieval failure: ${errMsg}`,
      });
    }
  });
};
