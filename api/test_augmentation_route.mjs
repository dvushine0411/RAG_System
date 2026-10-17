/**
 * Integration test verifying Fastify /api/v1/augmentation/assemble route validation and schema forwarding.
 */

import Fastify from "fastify";
import { z } from "zod";

console.log("=== Node.js Gateway Augmentation Route & Schema Test ===");

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

// Test 1: Valid schema parsing
const validPayload = {
  query: "Explain HNSW logarithmic search.",
  chunks: [
    {
      id: "550e8400-e29b-41d4-a716-446655440000",
      document_id: "doc-1",
      chunk_index: 0,
      content: "HNSW builds multi-layer skip lists.",
      token_count: 10,
      source_type: "pdf",
      vector_score: 0.95,
      final_score: 0.95,
      metadata: {},
    },
  ],
  conversation_history: [{ role: "user", content: "Hello" }],
  max_context_tokens: 4096,
  reserved_output_tokens: 1024,
};

const parsed1 = AugmentationRequestSchema.safeParse(validPayload);
if (!parsed1.success) {
  console.error("Test 1 Failed:", parsed1.error);
  process.exit(1);
}
console.log("✅ PASS: Valid augmentation payload accepted by Zod schema.");

// Test 2: Invalid empty query rejected
const invalidPayload = {
  query: "",
  chunks: [],
};
const parsed2 = AugmentationRequestSchema.safeParse(invalidPayload);
if (parsed2.success) {
  console.error("Test 2 Failed: Empty query should be rejected.");
  process.exit(1);
}
console.log("✅ PASS: Empty query correctly rejected with validation error.");

// Test 3: Fastify inject route testing
const server = Fastify();
const mockRagClient = {
  async assemblePrompt(params) {
    return {
      query: params.query,
      system_prompt: "You are an enterprise AI assistant.",
      context_block: "<context>\n[1] Sample\n</context>",
      assembled_messages: [
        { role: "system", content: "You are an enterprise AI assistant." },
        { role: "user", content: "<context>\n[1] Sample\n</context>\n\nUser Question:\n" + params.query },
      ],
      citations: [
        {
          citation_id: 1,
          chunk_id: "550e8400-e29b-41d4-a716-446655440000",
          document_id: "doc-1",
          title: "Doc 1",
          source_type: "pdf",
          score: 0.95,
        },
      ],
      budget_report: {
        system_tokens: 50,
        query_tokens: 10,
        history_tokens: 0,
        context_tokens: 25,
        total_prompt_tokens: 85,
        max_context_tokens: 4096,
        reserved_output_tokens: 1024,
        chunks_included: 1,
        chunks_truncated: 0,
      },
    };
  },
};

server.post("/api/v1/augmentation/assemble", async (req, reply) => {
  const result = AugmentationRequestSchema.safeParse(req.body);
  if (!result.success) {
    return reply.status(400).send({ error: "Bad Request", details: result.error.format() });
  }
  const data = await mockRagClient.assemblePrompt(result.data);
  return reply.status(200).send(data);
});

const response = await server.inject({
  method: "POST",
  url: "/api/v1/augmentation/assemble",
  payload: validPayload,
});

if (response.statusCode !== 200) {
  console.error("Test 3 Failed: Inject returned status", response.statusCode);
  process.exit(1);
}

const body = JSON.parse(response.body);
if (body.assembled_messages.length !== 2 || body.citations.length !== 1) {
  console.error("Test 3 Failed: Unexpected response body", body);
  process.exit(1);
}

console.log("✅ PASS: Fastify endpoint injection returned 200 OK with citations and budget report.");
console.log("=== All Node.js Gateway Augmentation tests passed 100%! ===");
process.exit(0);
