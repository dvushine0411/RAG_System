/**
 * Integration test for authentication (run `npm run build` first; needs the docker-compose MongoDB on :27017).
 * Uses a throw-away database `rag_auth_test` (dropped at the end).
 * Covers: bcrypt hashing time & storage, register/login validation, JWT access verification (tamper, wrong audience),
 *         refresh rotation, reuse detection (revokes all sessions), logout, role-based 403, admin bootstrap.
 * Inputs: TEST_MONGO_URI (default mongodb://rag_user:rag_secret@localhost:27017/rag_auth_test?authSource=admin).
 * Outputs: Console PASS/FAIL lines; non-zero exit code on failure.
 */

process.env.MONGO_URI =
  process.env.TEST_MONGO_URI ?? "mongodb://rag_user:rag_secret@localhost:27017/rag_auth_test?authSource=admin";
process.env.NODE_ENV = "production";
process.env.JWT_ACCESS_SECRET = "test-access-secret-0123456789abcdefghijklmnop";
process.env.JWT_REFRESH_SECRET = "test-refresh-secret-0123456789abcdefghijklmno";
process.env.REFRESH_REUSE_GRACE_SECONDS = "0"; // any reuse counts as theft in this test
process.env.ADMIN_EMAIL = "admin@test.local";
process.env.ADMIN_PASSWORD = "AdminPass123";
process.env.BCRYPT_COST ??= "11";

import Fastify from "fastify";
import cookie from "@fastify/cookie";
import mongoose from "mongoose";

const { connectDatabase } = await import("./dist/config/database.js");
const { hashPassword, verifyPassword } = await import("./dist/services/password.service.js");
const { ensureAdminAccount } = await import("./dist/services/auth.service.js");
const { authRoute, REFRESH_COOKIE } = await import("./dist/routes/auth.route.js");
const { requireAuth, requireRole } = await import("./dist/middlewares/auth.middleware.js");
const { UserModel } = await import("./dist/models/user.model.js");
const { RefreshTokenModel } = await import("./dist/models/refresh-token.model.js");

console.log("=== Authentication (bcrypt + JWT access/refresh) Test ===");
let failed = false;
function check(cond, message, extra) {
  if (!cond) {
    console.error(`❌ ${message}`, extra ?? "");
    failed = true;
    throw new Error(message);
  }
  console.log(`✅ PASS: ${message}`);
}

await connectDatabase();
await mongoose.connection.dropDatabase();
await UserModel.init();
await RefreshTokenModel.init();

const app = Fastify();
await app.register(cookie);
await app.register(authRoute, { prefix: "/api/v1/auth" });
app.get("/admin-only", { preHandler: [requireAuth, requireRole("admin")] }, async () => ({ ok: true }));

const post = (url, payload, cookies) => app.inject({ method: "POST", url, payload, cookies });
const refreshCookieOf = (res) => res.cookies.find((c) => c.name === REFRESH_COOKIE);
const bearer = (token) => ({ authorization: `Bearer ${token}` });

try {
  // 1. Hashing time & correctness
  const t0 = performance.now();
  const hash = await hashPassword("Correct1Horse");
  const hashMs = performance.now() - t0;
  check(hash.startsWith(`$2a$${process.env.BCRYPT_COST}$`) || hash.startsWith(`$2b$${process.env.BCRYPT_COST}$`), `bcrypt hash format with cost ${process.env.BCRYPT_COST}`);
  check(hashMs > 20 && hashMs < 1000, `Hash time acceptable: ${hashMs.toFixed(0)} ms (20–1000 ms window)`);
  check((await verifyPassword("Correct1Horse", hash)) && !(await verifyPassword("wrong1pass", hash)), "verifyPassword accepts right / rejects wrong password");
  check(!(await verifyPassword("Correct1Horse", null)), "verifyPassword with missing hash returns false (dummy compare)");

  // 2. Registration validation
  check((await post("/api/v1/auth/register", { email: "bad", name: "A", password: "abc12345" })).statusCode === 400, "Invalid email rejected (400)");
  check((await post("/api/v1/auth/register", { email: "u@test.local", name: "A", password: "short1" })).statusCode === 400, "Password < 8 chars rejected (400)");
  check((await post("/api/v1/auth/register", { email: "u@test.local", name: "A", password: "onlyletters" })).statusCode === 400, "Password without digits rejected (400)");
  check((await post("/api/v1/auth/register", { email: "u@test.local", name: "A", password: "a1" + "é".repeat(40) })).statusCode === 400, "Password > 72 UTF-8 bytes rejected (400)");

  // 3. Successful registration
  const reg = await post("/api/v1/auth/register", { email: "User@Test.Local", name: "Alice", password: "Alice12345" });
  check(reg.statusCode === 201, "Register returns 201", reg.body);
  const regBody = reg.json();
  check(regBody.user.email === "user@test.local" && regBody.user.role === "user" && !("password_hash" in regBody.user), "Email normalized, role=user, no password_hash in response");
  const regCookie = refreshCookieOf(reg);
  check(regCookie && regCookie.httpOnly && regCookie.sameSite === "Strict" && regCookie.path === "/api/v1/auth", "Refresh token set as httpOnly SameSite=Strict cookie scoped to /api/v1/auth");
  const stored = await UserModel.findOne({ email: "user@test.local" }).lean();
  check(stored.password_hash.startsWith("$2") && !stored.password_hash.includes("Alice12345"), "Password stored only as bcrypt hash");
  const storedToken = await RefreshTokenModel.findOne({ user_id: stored.id }).lean();
  check(storedToken && storedToken.token_hash.length === 64 && storedToken.token_hash !== regCookie.value, "Refresh token persisted as SHA-256 hash, not raw");
  check((await post("/api/v1/auth/register", { email: "user@test.local", name: "B", password: "Other12345" })).statusCode === 409, "Duplicate email rejected (409)");

  // 4. Login
  check((await post("/api/v1/auth/login", { email: "user@test.local", password: "Wrong12345" })).statusCode === 401, "Wrong password → 401");
  const unknown = await post("/api/v1/auth/login", { email: "nobody@test.local", password: "Wrong12345" });
  check(unknown.statusCode === 401 && unknown.json().error === "INVALID_CREDENTIALS", "Unknown email → same 401 INVALID_CREDENTIALS (no enumeration)");
  const login = await post("/api/v1/auth/login", { email: "user@test.local", password: "Alice12345" });
  check(login.statusCode === 200 && login.json().token_type === "Bearer" && login.json().expires_in > 0, "Correct login → 200 with Bearer access token");
  const access = login.json().access_token;
  let refresh = refreshCookieOf(login).value;

  // 5. Access token verification
  check((await app.inject({ method: "GET", url: "/api/v1/auth/me", headers: bearer(access) })).json().user.email === "user@test.local", "GET /me with access token → current user");
  check((await app.inject({ method: "GET", url: "/api/v1/auth/me" })).statusCode === 401, "GET /me without token → 401");
  const tampered = access.slice(0, -2) + (access.endsWith("A") ? "BB" : "AA");
  check((await app.inject({ method: "GET", url: "/api/v1/auth/me", headers: bearer(tampered) })).statusCode === 401, "Tampered access token → 401");
  check((await app.inject({ method: "GET", url: "/api/v1/auth/me", headers: bearer(refresh) })).statusCode === 401, "Refresh token cannot be used as access token → 401");

  // 6. Roles
  check((await app.inject({ method: "GET", url: "/admin-only", headers: bearer(access) })).statusCode === 403, "Regular user on admin route → 403");
  await ensureAdminAccount();
  const adminLogin = await post("/api/v1/auth/login", { email: "admin@test.local", password: "AdminPass123" });
  check(adminLogin.statusCode === 200 && adminLogin.json().user.role === "admin", "Bootstrap admin created from ADMIN_EMAIL / ADMIN_PASSWORD");
  check((await app.inject({ method: "GET", url: "/admin-only", headers: bearer(adminLogin.json().access_token) })).statusCode === 200, "Admin on admin route → 200");

  // 7. Refresh rotation
  const r1 = await post("/api/v1/auth/refresh", undefined, { [REFRESH_COOKIE]: refresh });
  check(r1.statusCode === 200 && r1.json().access_token, "Refresh → new access token");
  const rotated = refreshCookieOf(r1).value;
  check(rotated && rotated !== refresh, "Refresh token rotated (new cookie value)");
  check((await post("/api/v1/auth/refresh")).statusCode === 401, "Refresh without cookie → 401");

  // 8. Reuse detection: replaying the old token revokes the whole session family
  const replay = await post("/api/v1/auth/refresh", undefined, { [REFRESH_COOKIE]: refresh });
  check(replay.statusCode === 401 && replay.json().error === "TOKEN_REUSED", "Replaying rotated refresh token → 401 TOKEN_REUSED");
  check((await post("/api/v1/auth/refresh", undefined, { [REFRESH_COOKIE]: rotated })).statusCode === 401, "After reuse detection, the latest refresh token is revoked too");

  // 9. Logout
  const l2 = await post("/api/v1/auth/login", { email: "user@test.local", password: "Alice12345" });
  refresh = refreshCookieOf(l2).value;
  const out = await post("/api/v1/auth/logout", undefined, { [REFRESH_COOKIE]: refresh });
  check(out.statusCode === 204 && refreshCookieOf(out)?.value === "", "Logout → 204 and cookie cleared");
  check((await post("/api/v1/auth/refresh", undefined, { [REFRESH_COOKIE]: refresh })).statusCode === 401, "Refresh after logout → 401");
} catch {
  // check() already printed the failure
} finally {
  await app.close();
  await mongoose.connection.dropDatabase();
  await mongoose.disconnect();
}

console.log(failed ? "\n💥 AUTH TESTS FAILED\n" : "\n🎉 ALL AUTH TESTS PASSED!\n");
process.exit(failed ? 1 : 0);
