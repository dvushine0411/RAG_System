/**
 * api/src/config/env.config.ts
 * Environment variable validation using Zod.
 * Fails fast on startup if required variables are missing.
 * Ref: ARCHITECTURE.md §5 - dotenv + zod validation
 */

import { z } from "zod";
import "dotenv/config";

const EnvSchema = z.object({
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
  PORT: z.coerce.number().default(3000),

  // MongoDB
  MONGO_URI: z.string().url({ message: "MONGO_URI must be a valid MongoDB connection string" }),
  MONGO_SERVER_SELECTION_TIMEOUT_MS: z.coerce.number().int().positive().default(10000),

  // Python RAG Engine
  RAG_ENGINE_URL: z.string().url().default("http://rag_engine:8000"),

  // CORS
  CORS_ORIGIN: z.string().default("http://localhost"),

  // Upload limit for POST /api/v1/documents (bytes)
  MAX_UPLOAD_BYTES: z.coerce.number().int().positive().default(50 * 1024 * 1024),

  // Authentication — JWT (separate secrets so a leaked access secret cannot mint refresh tokens)
  JWT_ACCESS_SECRET: z.string().min(32, "JWT_ACCESS_SECRET must be at least 32 characters"),
  JWT_REFRESH_SECRET: z.string().min(32, "JWT_REFRESH_SECRET must be at least 32 characters"),
  JWT_ISSUER: z.string().default("rag-api"),
  JWT_ACCESS_TTL_SECONDS: z.coerce.number().int().positive().default(15 * 60),
  JWT_REFRESH_TTL_SECONDS: z.coerce.number().int().positive().default(7 * 24 * 60 * 60),
  // A rotated refresh token presented again within this window is treated as a concurrent refresh
  // (two tabs / double request), not as theft — only after it do we revoke the whole session family.
  REFRESH_REUSE_GRACE_SECONDS: z.coerce.number().int().min(0).default(10),
  // Secure cookies require HTTPS; keep false for plain http://localhost
  COOKIE_SECURE: z
    .enum(["true", "false"])
    .default("false")
    .transform((v) => v === "true"),

  // Password hashing — bcrypt cost factor (each +1 doubles hashing time; 11 ≈ 100–250 ms)
  BCRYPT_COST: z.coerce.number().int().min(10).max(15).default(11),

  // Optional bootstrap admin, created on startup if the email does not exist yet
  ADMIN_EMAIL: z.string().email().optional(),
  ADMIN_PASSWORD: z.string().min(8).optional(),
});

// Validate on module load — throws on misconfiguration
const parsed = EnvSchema.safeParse(process.env);

if (!parsed.success) {
  console.error("❌ Invalid environment configuration:");
  console.error(parsed.error.flatten().fieldErrors);
  process.exit(1);
}

export const envConfig = parsed.data;
export type EnvConfig = typeof envConfig;
