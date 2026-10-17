/**
 * System Role: Fastify route handlers exposing prompt assembly, context formatting, and citation generation with Zod validation.
 * Inputs: JSON HTTP POST payloads conforming to AugmentationRequestSchema.
 * Outputs: AugmentedPromptResponse containing formatted LLM messages, XML context, citations, and budget audits.
 * Ref: ARCHITECTURE.md §2.2 Phase B step 5, §5 Centralized Config Principle
 * Auth: requires a valid Bearer access token (requireAuth).
 */

import { FastifyInstance, FastifyPluginAsync } from "fastify";
import { z } from "zod";
import { ragEngineClient } from "../services/rag-engine.client.js";
import { logger } from "../config/logger.js";
import { requireAuth } from "../middlewares/auth.middleware.js";

const ChatMessageSchema = z.object({
  role: z.enum(["system", "user", "assistant"]),
  content: z.string().min(1, "Message content cannot be empty"),
});

const AugmentationRequestSchema = z.object({
  query: z.string().min(1, "Query string cannot be empty"),
  chunks: z.array(z.any()).default([]),
  conversation_history: z.array(ChatMessageSchema).optional(),
  custom_system_role: z.string().optional(),
  max_context_tokens: z.number().int().min(512).max(128000).optional(),
  reserved_output_tokens: z.number().int().min(128).max(8192).optional(),
});

export const augmentationRoute: FastifyPluginAsync = async (server: FastifyInstance) => {
  /**
   * POST /api/v1/augmentation/assemble
   * Assembles grounded prompt with strict anti-hallucination rules and citation mapping.
   */
  server.post("/assemble", { preHandler: requireAuth }, async (req, reply) => {
    const parseResult = AugmentationRequestSchema.safeParse(req.body);
    if (!parseResult.success) {
      return reply.status(400).send({
        error: "Bad Request",
        message: "Invalid augmentation request payload",
        details: parseResult.error.format(),
      });
    }

    const payload = parseResult.data;
    logger.info(`[AugmentationRoute] Assembling prompt for query: '${payload.query.substring(0, 50)}...'`);

    try {
      const response = await ragEngineClient.assemblePrompt(payload);
      return reply.status(200).send(response);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : String(err);
      logger.error(`[AugmentationRoute] Augmentation request failed: ${errMsg}`);
      return reply.status(502).send({
        error: "Bad Gateway",
        message: `RAG prompt augmentation failure: ${errMsg}`,
      });
    }
  });
};
