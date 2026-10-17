/**
 * api/src/server.ts
 * Fastify server entry point for the RAG API Gateway.
 * Connects to MongoDB, bootstraps the admin account, registers plugins and routes, then starts listening.
 * Inputs: envConfig (PORT, CORS_ORIGIN, MAX_UPLOAD_BYTES, MONGO_URI, JWT_*, ADMIN_*).
 * Outputs: HTTP server exposing /health, /api/v1/auth/* (public) and JWT-protected /api/v1/* endpoints.
 * Ref: ARCHITECTURE.md §7 API Service & Client Interface
 */

import Fastify from "fastify";
import { envConfig } from "./config/env.config.js";
import { logger } from "./config/logger.js";
import { connectDatabase, disconnectDatabase } from "./config/database.js";
import { ensureAdminAccount } from "./services/auth.service.js";

const server = Fastify({
  logger: false, // Using custom pino logger below
});

// ── Plugins ──────────────────────────────────────────────────────────
await server.register(import("@fastify/cors"), {
  origin: envConfig.CORS_ORIGIN,
  methods: ["GET", "POST", "DELETE"],
  credentials: true, // allow the httpOnly refresh-token cookie on cross-origin dev setups
});

await server.register(import("@fastify/cookie"));

// ── Health Check ──────────────────────────────────────────────────────
server.get("/health", async () => ({ status: "ok", service: "rag-api" }));

// ── Multipart & Routes ───────────────────────────────────────────────
await server.register(import("@fastify/multipart"), {
  limits: { fileSize: envConfig.MAX_UPLOAD_BYTES },
});

const { authRoute } = await import("./routes/auth.route.js");
const { documentsRoute } = await import("./routes/documents.route.js");
const { retrievalRoute } = await import("./routes/retrieval.route.js");
const { augmentationRoute } = await import("./routes/augmentation.route.js");
const { queryRoute } = await import("./routes/query.route.js");
const { adminRoute } = await import("./routes/admin.route.js");

await server.register(authRoute, { prefix: "/api/v1/auth" });
await server.register(documentsRoute, { prefix: "/api/v1" });
await server.register(retrievalRoute, { prefix: "/api/v1/retrieval" });
await server.register(augmentationRoute, { prefix: "/api/v1/augmentation" });
await server.register(queryRoute);
await server.register(adminRoute, { prefix: "/api/v1/admin" });

// ── Graceful Shutdown ─────────────────────────────────────────────────
for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, async () => {
    logger.info(`Received ${signal}, shutting down...`);
    await server.close();
    await disconnectDatabase();
    process.exit(0);
  });
}

// ── Start Server ──────────────────────────────────────────────────────
try {
  await connectDatabase();
  await ensureAdminAccount();
  const port = envConfig.PORT;
  await server.listen({ port, host: "0.0.0.0" });
  logger.info(`🚀 RAG API Gateway listening on port ${port}`);
} catch (err) {
  logger.error(err);
  process.exit(1);
}
