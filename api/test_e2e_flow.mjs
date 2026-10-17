/**
 * End-to-end system test against a RUNNING docker-compose stack, split into the real usage flows:
 *   AUTH                     : anonymous 401, admin login, user registration, duplicate/wrong-password errors,
 *                              user 403 on document management, refresh-token rotation via cookie, logout.
 *   ADMIN (quản trị tài liệu): health, upload md/txt/html, reject unsupported, list, dedup, Qdrant point count,
 *                              delete, verify vectors purged, 404 on unknown id.
 *   USER  (người hỏi đáp)    : SPA served by Nginx, streaming query through Nginx (SSE), scoped query
 *                              (filter.document_ids), multi-turn history, JSON query, retrieval search, validation.
 * Inputs: GATEWAY_URL (default http://localhost:3000), WEB_URL (default http://localhost),
 *         ENGINE_URL (default http://localhost:8000); ADMIN_EMAIL / ADMIN_PASSWORD (default: read from ../.env);
 *         files in ../test_docs/. Each run registers one user `<RUN_TAG>@e2e.local` (left in MongoDB).
 * Set E2E_SHOW_ANSWERS=1 to print each generated answer with its citations.
 * Outputs: Console PASS/FAIL lines; non-zero exit code on the first failure. Always cleans up uploaded docs.
 */

import { readFile } from "node:fs/promises";

const GATEWAY = (process.env.GATEWAY_URL ?? "http://localhost:3000").replace(/\/$/, "");
const WEB = (process.env.WEB_URL ?? "http://localhost").replace(/\/$/, "");
const ENGINE = (process.env.ENGINE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const RUN_TAG = `e2e-${Date.now()}`;
const SAMPLES = [
  { file: "sample.md", name: `${RUN_TAG}_guide.md`, type: "text/markdown", source_type: "markdown" },
  { file: "sample.txt", name: `${RUN_TAG}_notes.txt`, type: "text/plain", source_type: "text" },
  { file: "sample.html", name: `${RUN_TAG}_page.html`, type: "text/html", source_type: "html" },
];

let passed = 0;
const uploaded = []; // { id, title, content }

async function readDotEnv() {
  try {
    const text = await readFile(new URL("../.env", import.meta.url), "utf8");
    return Object.fromEntries(
      text.split("\n").filter((l) => /^[A-Z_]+=/.test(l)).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1).trim()])
    );
  } catch {
    return {};
  }
}
const dotEnv = await readDotEnv();
const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? dotEnv.ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? dotEnv.ADMIN_PASSWORD;
const USER_EMAIL = `${RUN_TAG}@e2e.local`;
const USER_PASSWORD = "E2eUser12345";

let ADMIN = null; // admin access token
let USER = null; // regular user access token
let userRefreshCookie = null; // "rag_refresh=..." for the user session

const SHOW_ANSWERS = process.env.E2E_SHOW_ANSWERS === "1";
function showAnswer(label, question, answer, citations) {
  if (!SHOW_ANSWERS) return;
  console.log(`\n     ┌─ ${label}`);
  console.log(`     │ Q: ${question}`);
  for (const line of answer.trim().split("\n")) console.log(`     │ A: ${line}`);
  for (const c of citations) {
    const where = [c.section_title && `§ ${c.section_title}`, c.page_number != null && `p.${c.page_number}`].filter(Boolean).join(", ");
    console.log(`     │ [${c.citation_id}] ${c.title ?? c.document_id}${where ? ` (${where})` : ""} — score ${Number(c.score).toFixed(3)}`);
  }
  console.log("     └─");
}

const auth = (token, headers = {}) => ({ ...headers, Authorization: `Bearer ${token}` });
const refreshCookieFrom = (res) => res.headers.getSetCookie().find((c) => c.startsWith("rag_refresh="))?.split(";")[0] ?? null;

function pass(message) {
  passed++;
  console.log(`  ✅ ${message}`);
}

class TestFailure extends Error {}
function fail(message, extra) {
  const detail = extra === undefined ? "" : ` → ${typeof extra === "string" ? extra : JSON.stringify(extra).slice(0, 600)}`;
  throw new TestFailure(`${message}${detail}`);
}

async function json(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

function uploadForm(name, content, type) {
  const form = new FormData();
  form.append("file", new Blob([content], { type }), name);
  return form;
}

function parseSse(text) {
  return text
    .replace(/\r\n/g, "\n")
    .split("\n\n")
    .filter((b) => b.trim())
    .map((block) => {
      const event = block.match(/^event: (.*)$/m)?.[1] ?? "message";
      const data = block
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trim())
        .join("\n");
      return { event, data: data ? JSON.parse(data) : null };
    });
}

async function streamQuery(base, body, token = USER) {
  const res = await fetch(`${base}/api/v1/query/stream`, {
    method: "POST",
    headers: auth(token, { "Content-Type": "application/json", Accept: "text/event-stream" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) fail(`Stream query HTTP ${res.status}`, await json(res));
  if (!res.headers.get("content-type")?.includes("text/event-stream")) fail("Stream query wrong content-type", res.headers.get("content-type"));
  const frames = parseSse(await res.text());
  const error = frames.find((f) => f.event === "error");
  if (error) fail("SSE error frame", error.data);
  return {
    frames,
    answer: frames.filter((f) => f.event === "token").map((f) => f.data.delta).join(""),
    citations: frames.find((f) => f.event === "citations")?.data.citations ?? [],
    done: frames.find((f) => f.event === "done")?.data,
  };
}

async function pointCount() {
  const info = await json(await fetch(`${ENGINE}/api/v1/vectors/collection/info`));
  if (typeof info.vectors_count !== "number") fail("Collection info unavailable", info);
  return info;
}

async function authFlow() {
  console.log("\n▶ AUTH FLOW — đăng ký / đăng nhập / JWT");
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) fail("ADMIN_EMAIL / ADMIN_PASSWORD not found in env or ../.env");

  const anon = await fetch(`${WEB}/api/v1/documents`).catch((e) => fail(`Web UI unreachable at ${WEB}`, e.message));
  if (anon.status !== 401) fail(`Anonymous request expected 401, got ${anon.status}`);
  pass("Anonymous request to protected API → 401.");

  const postJson = (path, body, headers = {}) =>
    fetch(`${WEB}/api/v1/auth${path}`, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json", ...headers } : headers,
      body: body && JSON.stringify(body),
    });

  const adminRes = await postJson("/login", { email: ADMIN_EMAIL, password: ADMIN_PASSWORD });
  const adminBody = await json(adminRes);
  if (adminRes.status !== 200 || adminBody.user?.role !== "admin" || !refreshCookieFrom(adminRes)) fail("Admin login failed", adminBody);
  ADMIN = adminBody.access_token;
  pass(`Admin '${ADMIN_EMAIL}' logged in via Nginx (role=admin, refresh cookie set).`);

  const t0 = performance.now();
  const regRes = await postJson("/register", { email: USER_EMAIL, name: "E2E User", password: USER_PASSWORD });
  const regMs = performance.now() - t0;
  const regBody = await json(regRes);
  if (regRes.status !== 201 || regBody.user?.role !== "user") fail("User registration failed", regBody);
  USER = regBody.access_token;
  userRefreshCookie = refreshCookieFrom(regRes);
  const setCookie = regRes.headers.getSetCookie().find((c) => c.startsWith("rag_refresh=")) ?? "";
  if (!/HttpOnly/i.test(setCookie) || !/SameSite=Strict/i.test(setCookie) || !/Path=\/api\/v1\/auth/i.test(setCookie)) fail("Refresh cookie flags wrong", setCookie);
  pass(`Registered '${USER_EMAIL}' (role=user) in ${Math.round(regMs)} ms incl. bcrypt; cookie HttpOnly + SameSite=Strict + Path=/api/v1/auth.`);

  if ((await postJson("/register", { email: USER_EMAIL, name: "Dup", password: USER_PASSWORD })).status !== 409) fail("Duplicate email not rejected");
  if ((await postJson("/login", { email: USER_EMAIL, password: "Wrong12345" })).status !== 401) fail("Wrong password not rejected");
  if ((await postJson("/register", { email: `w-${USER_EMAIL}`, name: "Weak", password: "weak" })).status !== 400) fail("Weak password not rejected");
  pass("Duplicate email → 409, wrong password → 401, weak password → 400.");

  const me = await json(await fetch(`${WEB}/api/v1/auth/me`, { headers: auth(USER) }));
  if (me.user?.email !== USER_EMAIL) fail("GET /auth/me failed", me);
  pass("GET /api/v1/auth/me returns the logged-in user.");

  const upUser = await fetch(`${GATEWAY}/api/v1/documents`, { method: "POST", headers: auth(USER), body: uploadForm(`${RUN_TAG}_user.md`, "# user", "text/markdown") });
  const delUser = await fetch(`${GATEWAY}/api/v1/documents/00000000-0000-0000-0000-000000000000`, { method: "DELETE", headers: auth(USER) });
  if (upUser.status !== 403 || delUser.status !== 403) fail(`User document management expected 403/403, got ${upUser.status}/${delUser.status}`);
  pass("Role 'user' → 403 on upload and delete.");

  const refRes = await postJson("/refresh", undefined, { Cookie: userRefreshCookie });
  const refBody = await json(refRes);
  const rotated = refreshCookieFrom(refRes);
  if (refRes.status !== 200 || !refBody.access_token || !rotated || rotated === userRefreshCookie) fail("Refresh rotation failed", refBody);
  USER = refBody.access_token;
  userRefreshCookie = rotated;
  pass("POST /auth/refresh via cookie → new access token + rotated refresh cookie.");
}

async function authLogout() {
  console.log("\n▶ AUTH FLOW — đăng xuất");
  const out = await fetch(`${WEB}/api/v1/auth/logout`, { method: "POST", headers: { Cookie: userRefreshCookie } });
  if (out.status !== 204) fail(`Logout expected 204, got ${out.status}`);
  const after = await fetch(`${WEB}/api/v1/auth/refresh`, { method: "POST", headers: { Cookie: userRefreshCookie } });
  if (after.status !== 401) fail(`Refresh after logout expected 401, got ${after.status}`);
  pass("Logout → 204; refresh token no longer accepted (401).");
}

async function adminFlow() {
  console.log("\n▶ ADMIN FLOW — quản trị tài liệu");

  const gw = await fetch(`${GATEWAY}/health`).catch((e) => fail(`Gateway unreachable at ${GATEWAY}`, e.message));
  if (!gw.ok) fail("Gateway /health", gw.status);
  const eng = await fetch(`${ENGINE}/health`).catch((e) => fail(`RAG Engine unreachable at ${ENGINE}`, e.message));
  if (!eng.ok) fail("RAG Engine /health", eng.status);
  pass("API Gateway & RAG Engine healthy.");

  const before = await pointCount();
  pass(`Qdrant collection '${before.name}' ready (dim=${before.dimension}, ${before.distance}, M=${before.hnsw_m}, points=${before.vectors_count}).`);

  let totalChunks = 0;
  for (const s of SAMPLES) {
    const content = (await readFile(new URL(`../test_docs/${s.file}`, import.meta.url), "utf8")) + `\n\n${RUN_TAG}\n`;
    const res = await fetch(`${GATEWAY}/api/v1/documents`, { method: "POST", headers: auth(ADMIN), body: uploadForm(s.name, content, s.type) });
    const body = await json(res);
    if (res.status !== 201) fail(`Upload ${s.file} HTTP ${res.status}`, body);
    const d = body.document;
    if (d.status !== "completed" || d.total_chunks < 1 || d.source_type !== s.source_type) fail(`Upload ${s.file} unexpected record`, d);
    uploaded.push({ id: d.id, title: d.title, content });
    totalChunks += d.total_chunks;
    pass(`Uploaded ${s.file} → source_type=${d.source_type}, ${d.total_chunks} chunks, ${d.total_tokens} tokens.`);
  }

  const after = await pointCount();
  if (after.vectors_count < before.vectors_count + totalChunks) fail("Qdrant point count did not grow by uploaded chunks", { before: before.vectors_count, after: after.vectors_count, totalChunks });
  pass(`Qdrant points ${before.vectors_count} → ${after.vectors_count} (+${totalChunks}).`);

  const bad = await fetch(`${GATEWAY}/api/v1/documents`, { method: "POST", headers: auth(ADMIN), body: uploadForm(`${RUN_TAG}.exe`, "MZ", "application/octet-stream") });
  if (bad.status !== 415) fail(`Unsupported upload expected 415, got ${bad.status}`, await json(bad));
  pass("Unsupported file type (.exe) rejected with 415.");

  const list = await json(await fetch(`${GATEWAY}/api/v1/documents`, { headers: auth(ADMIN) }));
  for (const u of uploaded) if (!list.documents?.some((d) => d.id === u.id)) fail(`List missing ${u.title}`, list);
  pass(`GET /api/v1/documents lists all ${uploaded.length} uploaded documents.`);

  const dupRes = await fetch(`${GATEWAY}/api/v1/documents`, { method: "POST", headers: auth(ADMIN), body: uploadForm("copy_of_guide.md", uploaded[0].content, "text/markdown") });
  const dup = await json(dupRes);
  if (dupRes.status !== 200 || !dup.is_duplicate || dup.document.id !== uploaded[0].id) fail("Dedup failed", dup);
  const afterDup = await pointCount();
  if (afterDup.vectors_count !== after.vectors_count) fail("Duplicate upload created new vectors", afterDup);
  pass("Duplicate content (renamed file) returns existing document; no new vectors.");
}

async function userFlow() {
  console.log("\n▶ USER FLOW — người dùng hỏi đáp qua giao diện (Nginx)");

  const html = await (await fetch(`${WEB}/`).catch((e) => fail(`Web UI unreachable at ${WEB}`, e.message))).text();
  if (!html.includes('<div id="root">')) fail("SPA index.html not served", html.slice(0, 200));
  const asset = html.match(/src="(\/assets\/[^"]+\.js)"/)?.[1];
  if (!asset || !(await fetch(`${WEB}${asset}`)).ok) fail("SPA JS bundle not served", asset);
  const deep = await fetch(`${WEB}/some/client/route`);
  if (!deep.ok || !(await deep.text()).includes('<div id="root">')) fail("SPA fallback not working");
  pass(`SPA served by Nginx (bundle ${asset}, deep-link fallback OK).`);

  const viaNginx = await json(await fetch(`${WEB}/api/v1/documents`, { headers: auth(USER) }));
  if (!Array.isArray(viaNginx.documents)) fail("Nginx /api proxy failed", viaNginx);
  pass("Nginx proxies /api → API Gateway.");

  const Q1 = "What is the chunking strategy and chunk size?";
  const all = await streamQuery(WEB, { query: Q1 });
  if (!all.answer || !all.done) fail("Streaming answer empty or missing done", all.frames.map((f) => f.event));
  if (all.citations.length === 0) fail("No citations returned for corpus-wide query");
  showAnswer("USER · stream /api/v1/query/stream (all documents)", Q1, all.answer, all.citations);
  pass(`Streaming query via Nginx: ${all.frames.filter((f) => f.event === "token").length} token frames, ${all.citations.length} citations, ${Math.round(all.done.latency_ms)} ms.`);

  const target = uploaded[1];
  const scoped = await streamQuery(WEB, { query: "Summarize this document.", filter: { document_ids: [target.id] } });
  if (scoped.citations.length === 0) fail("Scoped query returned no citations");
  if (scoped.citations.some((c) => c.document_id !== target.id)) fail("Scoped query cited other documents", scoped.citations);
  showAnswer(`USER · scoped to '${target.title}'`, "Summarize this document.", scoped.answer, scoped.citations);
  pass(`Scoped query (only '${target.title}'): all ${scoped.citations.length} citations from the selected document.`);

  const followUp = await streamQuery(WEB, {
    query: "And how is deduplication handled?",
    conversation_history: [
      { role: "user", content: "What is the chunking strategy and chunk size?" },
      { role: "assistant", content: all.answer },
    ],
  });
  if (!followUp.answer || !followUp.done) fail("Multi-turn follow-up failed");
  showAnswer("USER · multi-turn follow-up", "And how is deduplication handled?", followUp.answer, followUp.citations);
  pass("Multi-turn follow-up with conversation_history answered.");

  const qRes = await fetch(`${GATEWAY}/api/v1/query`, {
    method: "POST",
    headers: auth(USER, { "Content-Type": "application/json" }),
    body: JSON.stringify({ query: "What is HNSW used for?" }),
  });
  const q = await json(qRes);
  if (qRes.status !== 200 || !q.answer || !Array.isArray(q.citations) || !q.token_usage) fail("JSON query failed", q);
  showAnswer("USER · JSON /api/v1/query", "What is HNSW used for?", q.answer, q.citations);
  pass(`POST /api/v1/query (JSON): ${q.answer.length} chars, ${q.citations.length} citations, ${q.token_usage.total_tokens} tokens.`);

  const QA = "How does the ingestion pipeline parse documents?";
  const adminAns = await streamQuery(WEB, { query: QA }, ADMIN);
  if (!adminAns.answer || !adminAns.done || adminAns.citations.length === 0) fail("Admin streaming query failed", adminAns.frames.map((f) => f.event));
  showAnswer("ADMIN · stream /api/v1/query/stream", QA, adminAns.answer, adminAns.citations);
  pass(`Admin can also query: ${adminAns.citations.length} citations, ${adminAns.done.token_usage.total_tokens} tokens.`);

  const sRes = await fetch(`${GATEWAY}/api/v1/retrieval/search`, {
    method: "POST",
    headers: auth(USER, { "Content-Type": "application/json" }),
    body: JSON.stringify({ query: "deduplication SHA-256", filter: { document_ids: uploaded.map((u) => u.id) }, top_k: 10, top_n: 3 }),
  });
  const s = await json(sRes);
  if (sRes.status !== 200 || s.returned_count < 1 || s.results.some((r) => !uploaded.some((u) => u.id === r.document_id))) fail("Retrieval search failed", s);
  pass(`Retrieval search: ${s.total_candidates} candidates → ${s.returned_count} reranked (fallback=${s.fallback_used}).`);

  const empty = await fetch(`${WEB}/api/v1/query/stream`, { method: "POST", headers: auth(USER, { "Content-Type": "application/json" }), body: JSON.stringify({ query: "" }) });
  if (empty.status !== 400) fail(`Empty query expected 400, got ${empty.status}`);
  pass("Empty question rejected with 400.");
}

async function adminCleanup() {
  console.log("\n▶ ADMIN FLOW — xoá tài liệu");
  const before = await pointCount();
  while (uploaded.length > 0) {
    const u = uploaded.pop();
    const res = await fetch(`${GATEWAY}/api/v1/documents/${u.id}`, { method: "DELETE", headers: auth(ADMIN) });
    if (res.status !== 200) fail(`Delete ${u.title} HTTP ${res.status}`, await json(res));
    const s = await json(
      await fetch(`${GATEWAY}/api/v1/retrieval/search`, {
        method: "POST",
        headers: auth(ADMIN, { "Content-Type": "application/json" }),
        body: JSON.stringify({ query: "RAG", filter: { document_ids: [u.id] } }),
      })
    );
    if (s.returned_count !== 0) fail(`Vectors of ${u.title} still searchable after delete`, s);
    pass(`Deleted '${u.title}' — MongoDB record and Qdrant vectors gone.`);
  }
  const after = await pointCount();
  pass(`Qdrant points ${before.vectors_count} → ${after.vectors_count}.`);

  const list = await json(await fetch(`${GATEWAY}/api/v1/documents`, { headers: auth(ADMIN) }));
  if (list.documents.some((d) => d.title.startsWith(RUN_TAG))) fail("Deleted documents still listed");
  const missing = await fetch(`${GATEWAY}/api/v1/documents/00000000-0000-0000-0000-000000000000`, { method: "DELETE", headers: auth(ADMIN) });
  if (missing.status !== 404) fail(`Delete unknown id expected 404, got ${missing.status}`);
  pass("Deleted documents no longer listed; unknown id → 404.");
}

console.log(`=== RAG System E2E — gateway ${GATEWAY} | web ${WEB} | engine ${ENGINE} ===`);
let exitCode = 0;
try {
  await authFlow();
  await adminFlow();
  await userFlow();
  await authLogout();
} catch (err) {
  console.error(`  ❌ ${err instanceof TestFailure ? err.message : err.stack}`);
  exitCode = 1;
} finally {
  try {
    if (ADMIN) await adminCleanup();
  } catch (err) {
    console.error(`  ❌ cleanup: ${err instanceof TestFailure ? err.message : err.stack}`);
    exitCode = 1;
  }
}
console.log(exitCode === 0 ? `\n🎉 ALL ${passed} E2E CHECKS PASSED\n` : `\n💥 E2E FAILED after ${passed} passing checks\n`);
process.exit(exitCode);
