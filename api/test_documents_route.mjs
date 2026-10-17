/**
 * Integration test for the compiled document routes (run `npm run build` first).
 * Verifies source_type normalization, unsupported-type rejection (415), deduplication,
 * retry of previously failed ingestions, and admin-only upload/delete — with Mongoose and the RAG Engine stubbed out.
 * Inputs: dist/routes/documents.route.js, stubbed DocumentModel and ragEngineClient.
 * Outputs: Console PASS/FAIL lines; non-zero exit code on failure.
 */

process.env.MONGO_URI ??= "mongodb://localhost:27017/rag_test";
process.env.NODE_ENV = "production";
process.env.JWT_ACCESS_SECRET ??= "test-access-secret-0123456789abcdefghijklmnop";
process.env.JWT_REFRESH_SECRET ??= "test-refresh-secret-0123456789abcdefghijklmno";

import Fastify from "fastify";
import multipart from "@fastify/multipart";

const { DocumentModel } = await import("./dist/models/document.model.js");
const { ragEngineClient } = await import("./dist/services/rag-engine.client.js");
const { documentsRoute } = await import("./dist/routes/documents.route.js");
const { resolveSourceType } = await import("./dist/utils/source-type.js");
const { signAccessToken } = await import("./dist/services/token.service.js");
const ADMIN_TOKEN = signAccessToken({ sub: "a1", email: "admin@test.local", role: "admin" });
const USER_TOKEN = signAccessToken({ sub: "u1", email: "user@test.local", role: "user" });

console.log("=== Node.js Gateway Documents Route Test ===");

function fail(message, extra) {
  console.error(`❌ ${message}`, extra ?? "");
  process.exit(1);
}

// ── In-memory stubs for Mongoose and the RAG Engine ─────────────────
const store = new Map(); // file_hash -> plain doc
DocumentModel.prototype.save = async function () {
  store.set(this.file_hash, this);
  return this;
};
DocumentModel.findOne = (query) => ({
  exec: async () =>
    query.file_hash ? store.get(query.file_hash) ?? null : [...store.values()].find((d) => d.id === query.id) ?? null,
});
DocumentModel.deleteOne = (query) => ({
  exec: async () => {
    for (const [hash, doc] of store) if (doc.id === query.id) store.delete(hash);
  },
});

let processCalls = [];
let failNextProcess = false;
ragEngineClient.processAndIndex = async (buffer, filename, documentId, options) => {
  processCalls.push({ filename, documentId, options });
  if (failNextProcess) {
    failNextProcess = false;
    throw new Error("engine down");
  }
  return { document_id: documentId, filename, source_type: options.sourceType, total_chunks: 3, total_tokens: 42, collection_name: "document_chunks", status: "indexed" };
};

const app = Fastify();
await app.register(multipart);
await app.register(documentsRoute, { prefix: "/api/v1" });

function upload(filename, content, token = ADMIN_TOKEN) {
  const boundary = "----ragtestboundary";
  const payload =
    `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${filename}"\r\n` +
    `Content-Type: application/octet-stream\r\n\r\n${content}\r\n--${boundary}--\r\n`;
  return app.inject({
    method: "POST",
    url: "/api/v1/documents",
    headers: { "content-type": `multipart/form-data; boundary=${boundary}`, authorization: `Bearer ${token}` },
    payload,
  });
}

// Test 1: extension mapping
if (resolveSourceType("a.md") !== "markdown" || resolveSourceType("b.TXT") !== "text" || resolveSourceType("c.htm") !== "html") {
  fail("Test 1 Failed: resolveSourceType mapping");
}
if (resolveSourceType("noext") !== null || resolveSourceType("x.exe") !== null) fail("Test 1 Failed: unsupported should be null");
console.log("✅ PASS: resolveSourceType maps extensions to canonical MongoDB source types.");

// Test 2: unsupported type rejected before touching storage
const res415 = await upload("virus.exe", "MZ");
if (res415.statusCode !== 415 || processCalls.length !== 0) fail("Test 2 Failed", res415.body);
console.log("✅ PASS: Unsupported extension rejected with 415.");

// Test 3: markdown upload stored with canonical source_type
const res201 = await upload("notes.md", "# Title\nHello RAG");
if (res201.statusCode !== 201) fail("Test 3 Failed: status", res201.body);
const created = res201.json().document;
if (created.source_type !== "markdown" || created.total_chunks !== 3) fail("Test 3 Failed: body", created);
if (processCalls[0].options.sourceType !== "markdown") fail("Test 3 Failed: engine got wrong sourceType", processCalls[0]);
console.log("✅ PASS: .md upload indexed with source_type 'markdown'.");

// Test 4: identical content deduplicated
const resDup = await upload("copy.md", "# Title\nHello RAG");
if (resDup.statusCode !== 200 || resDup.json().is_duplicate !== true || processCalls.length !== 1) fail("Test 4 Failed", resDup.body);
console.log("✅ PASS: Duplicate content returns 200 with is_duplicate=true.");

// Test 5: failed ingestion can be retried
failNextProcess = true;
const resFail = await upload("doc.txt", "retry me");
if (resFail.statusCode !== 502) fail("Test 5 Failed: expected 502", resFail.body);
const resRetry = await upload("doc.txt", "retry me");
if (resRetry.statusCode !== 201 || resRetry.json().is_duplicate !== false) fail("Test 5 Failed: retry", resRetry.body);
console.log("✅ PASS: Previously failed document is re-ingested instead of deduplicated.");

// Test 6: role enforcement
const callsBefore = processCalls.length;
const resUser = await upload("user.md", "# by user", USER_TOKEN);
const resDelUser = await app.inject({ method: "DELETE", url: `/api/v1/documents/${created.id}`, headers: { authorization: `Bearer ${USER_TOKEN}` } });
if (resUser.statusCode !== 403 || resDelUser.statusCode !== 403 || processCalls.length !== callsBefore) fail("Test 6 Failed: user could manage documents", [resUser.statusCode, resDelUser.statusCode]);
const resAnon = await app.inject({ method: "GET", url: "/api/v1/documents" });
if (resAnon.statusCode !== 401) fail("Test 6 Failed: anonymous list allowed", resAnon.statusCode);
console.log("✅ PASS: Role 'user' gets 403 on upload/delete; anonymous list gets 401.");

await app.close();
console.log("\n🎉 ALL DOCUMENTS ROUTE TESTS PASSED!\n");
