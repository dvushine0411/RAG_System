/**
 * Integration test for the compiled query routes (run `npm run build` first).
 * Verifies SSE frame parsing, non-streaming POST /api/v1/query aggregation, error propagation,
 * that the `filter` field is forwarded to the RAG Engine unchanged, and that a valid access token is required.
 * Inputs: dist/services/sse-collector.js, dist/routes/query.route.js with a stubbed ragEngineClient.
 * Outputs: Console PASS/FAIL lines; non-zero exit code on failure.
 */

process.env.MONGO_URI ??= "mongodb://localhost:27017/rag_test";
process.env.NODE_ENV = "production"; // plain pino output, no pino-pretty transport
process.env.JWT_ACCESS_SECRET ??= "test-access-secret-0123456789abcdefghijklmnop";
process.env.JWT_REFRESH_SECRET ??= "test-refresh-secret-0123456789abcdefghijklmno";

import Fastify from "fastify";

const { parseSseFrames, collectSseAnswer } = await import("./dist/services/sse-collector.js");
const { ragEngineClient } = await import("./dist/services/rag-engine.client.js");
const { queryRoute } = await import("./dist/routes/query.route.js");
const { signAccessToken } = await import("./dist/services/token.service.js");
const { QueryLogModel } = await import("./dist/models/query-log.model.js");
const queryLogs = [];
QueryLogModel.create = async (doc) => {
  queryLogs.push(doc);
  return doc;
};
const AUTH = { authorization: `Bearer ${signAccessToken({ sub: "u1", email: "u@test.local", role: "user" })}` };

console.log("=== Node.js Gateway Query Route (JSON + SSE) Test ===");

function fail(message, extra) {
  console.error(`❌ ${message}`, extra ?? "");
  process.exit(1);
}

function streamFrom(chunks) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
}

const SSE_OK = [
  'event: citations\ndata: {"citations":[{"citation_id":1,"chunk_id":"c1","document_id":"d1","source_type":"pdf","score":0.9}]}\n\n',
  'event: token\ndata: {"delta":"HNSW là "}\n\nevent: tok',
  'en\ndata: {"delta":"đồ thị [1]."}\n\n',
  'event: done\ndata: {"finish_reason":"stop","token_usage":{"prompt_tokens":10,"completion_tokens":4,"total_tokens":14},"latency_ms":12.5}\n\n',
];

// Test 1: frame parser keeps incomplete trailing frame
const parsed = parseSseFrames('event: token\ndata: {"delta":"a"}\n\nevent: tok');
if (parsed.frames.length !== 1 || parsed.rest !== "event: tok") fail("Test 1 Failed: parseSseFrames", parsed);
console.log("✅ PASS: parseSseFrames splits complete frames and keeps the remainder.");

// Test 2: collector aggregates frames split across chunk boundaries
const collected = await collectSseAnswer(streamFrom(SSE_OK));
if (collected.answer !== "HNSW là đồ thị [1].") fail("Test 2 Failed: answer", collected);
if (collected.citations.length !== 1 || collected.token_usage?.total_tokens !== 14) fail("Test 2 Failed: metadata", collected);
console.log("✅ PASS: collectSseAnswer aggregates tokens, citations and usage.");

// Test 3: collector throws on error frame
try {
  await collectSseAnswer(streamFrom(['event: error\ndata: {"message":"boom","error_code":"X"}\n\n']));
  fail("Test 3 Failed: expected error to be thrown");
} catch (err) {
  if (!String(err.message).includes("boom")) fail("Test 3 Failed: wrong error", err);
}
console.log("✅ PASS: collectSseAnswer surfaces 'error' frames as exceptions.");

// Stub the upstream RAG Engine call
let lastPayload = null;
ragEngineClient.streamQuery = async (payload) => {
  lastPayload = payload;
  return new Response(streamFrom(SSE_OK), { headers: { "Content-Type": "text/event-stream" } });
};

const app = Fastify();
await app.register(queryRoute);

// Test 4: POST /api/v1/query returns aggregated JSON and forwards `filter`
const res = await app.inject({
  method: "POST",
  url: "/api/v1/query",
  headers: AUTH,
  payload: { query: "HNSW là gì?", filter: { document_ids: ["d1"] } },
});
if (res.statusCode !== 200) fail("Test 4 Failed: status", res.body);
const body = res.json();
if (body.answer !== "HNSW là đồ thị [1]." || body.query !== "HNSW là gì?") fail("Test 4 Failed: body", body);
if (lastPayload?.filter?.document_ids?.[0] !== "d1") fail("Test 4 Failed: filter not forwarded", lastPayload);
console.log("✅ PASS: POST /api/v1/query returns aggregated JSON answer and forwards filter.");

// Test 5: POST /api/v1/query/stream pipes SSE frames
const streamRes = await app.inject({ method: "POST", url: "/api/v1/query/stream", headers: AUTH, payload: { query: "HNSW?" } });
if (streamRes.statusCode !== 200 || !streamRes.headers["content-type"].includes("text/event-stream")) {
  fail("Test 5 Failed: headers", streamRes.headers);
}
if (!streamRes.body.includes("event: done")) fail("Test 5 Failed: body", streamRes.body);
console.log("✅ PASS: POST /api/v1/query/stream pipes SSE frames to the client.");

// Test 6: empty query rejected
const badRes = await app.inject({ method: "POST", url: "/api/v1/query", headers: AUTH, payload: { query: "" } });
if (badRes.statusCode !== 400) fail("Test 6 Failed: expected 400", badRes.statusCode);
console.log("✅ PASS: Empty query rejected with 400.");

// Test 7: missing / invalid token rejected before reaching the RAG Engine
lastPayload = null;
const noAuth = await app.inject({ method: "POST", url: "/api/v1/query/stream", payload: { query: "HNSW?" } });
const badAuth = await app.inject({ method: "POST", url: "/api/v1/query", headers: { authorization: "Bearer not-a-jwt" }, payload: { query: "HNSW?" } });
if (noAuth.statusCode !== 401 || badAuth.statusCode !== 401 || lastPayload !== null) fail("Test 7 Failed: unauthenticated request not rejected", [noAuth.statusCode, badAuth.statusCode]);
console.log("✅ PASS: Requests without a valid access token are rejected with 401.");

// Test 8: monitoring — one query_logs record per answered query, validator-compatible fields
await new Promise((r) => setTimeout(r, 50)); // stream 'end' handlers run asynchronously
const streamLog = queryLogs.find((l) => l.endpoint === "stream" && l.status === "success");
const jsonLog = queryLogs.find((l) => l.endpoint === "json" && l.status === "success");
if (!streamLog || !jsonLog) fail("Test 8 Failed: missing query logs", queryLogs);
if (!Number.isInteger(streamLog.latency_ms) || !Number.isInteger(streamLog.ttft_ms)) fail("Test 8 Failed: latency/ttft must be ints", streamLog);
if (streamLog.generated_response !== "HNSW là đồ thị [1]." || streamLog.retrieved_chunk_ids[0] !== "c1" || streamLog.rerank_scores.c1 !== 0.9) fail("Test 8 Failed: content", streamLog);
if (streamLog.token_usage.total_tokens !== 14 || streamLog.user_id !== "u1" || jsonLog.filter_document_ids?.[0] !== "d1") fail("Test 8 Failed: usage/user/filter", [streamLog, jsonLog]);
if (queryLogs.some((l) => l.user_query === "")) fail("Test 8 Failed: rejected requests must not be logged");
console.log(`✅ PASS: query_logs records written for stream + JSON (latency ${streamLog.latency_ms} ms, TTFT ${streamLog.ttft_ms} ms, tokens, chunk scores).`);

await app.close();
console.log("\n🎉 ALL QUERY ROUTE TESTS PASSED!\n");
