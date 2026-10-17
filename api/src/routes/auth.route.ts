/**
 * System Role: Fastify routes for account registration and JWT session management.
 * Inputs: JSON bodies validated by Zod; refresh token from the httpOnly `rag_refresh` cookie.
 * Outputs: { user, access_token, token_type, expires_in } + Set-Cookie (refresh token), or error JSON.
 * Endpoints (prefix /api/v1/auth): POST /register, POST /login, POST /refresh, POST /logout, GET /me
 */

import { Buffer } from "node:buffer";
import type { FastifyInstance, FastifyPluginAsync, FastifyReply } from "fastify";
import { z } from "zod";
import { envConfig } from "../config/env.config.js";
import { logger } from "../config/logger.js";
import { requireAuth } from "../middlewares/auth.middleware.js";
import * as authService from "../services/auth.service.js";
import type { AuthSession } from "../services/auth.service.js";
import { BCRYPT_MAX_PASSWORD_BYTES } from "../services/password.service.js";
import { AuthError } from "../utils/auth-error.js";

export const REFRESH_COOKIE = "rag_refresh";
const REFRESH_COOKIE_PATH = "/api/v1/auth";

const PasswordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .refine((p) => Buffer.byteLength(p, "utf8") <= BCRYPT_MAX_PASSWORD_BYTES, {
    message: `Password must be at most ${BCRYPT_MAX_PASSWORD_BYTES} bytes`,
  })
  .refine((p) => /[A-Za-z]/.test(p) && /\d/.test(p), { message: "Password must contain letters and digits" });

const RegisterSchema = z.object({
  email: z.string().trim().email("Invalid email").max(254),
  name: z.string().trim().min(1, "Name is required").max(100),
  password: PasswordSchema,
});

const LoginSchema = z.object({
  email: z.string().trim().email("Invalid email"),
  password: z.string().min(1, "Password is required").max(1024),
});

function setRefreshCookie(reply: FastifyReply, session: AuthSession) {
  reply.setCookie(REFRESH_COOKIE, session.refresh.token, {
    httpOnly: true,
    secure: envConfig.COOKIE_SECURE,
    sameSite: "strict",
    path: REFRESH_COOKIE_PATH,
    expires: session.refresh.expiresAt,
  });
}

function clearRefreshCookie(reply: FastifyReply) {
  reply.clearCookie(REFRESH_COOKIE, { path: REFRESH_COOKIE_PATH });
}

function sessionBody(session: AuthSession) {
  return {
    user: session.user,
    access_token: session.accessToken,
    token_type: "Bearer",
    expires_in: envConfig.JWT_ACCESS_TTL_SECONDS,
  };
}

function sendError(reply: FastifyReply, err: unknown) {
  if (err instanceof AuthError) {
    return reply.status(err.statusCode).send({ error: err.code, message: err.message });
  }
  logger.error(`[AuthRoute] Unexpected error: ${err instanceof Error ? err.stack : String(err)}`);
  return reply.status(500).send({ error: "INTERNAL_ERROR", message: "Unexpected authentication error." });
}

export const authRoute: FastifyPluginAsync = async (server: FastifyInstance) => {
  server.post("/register", async (req, reply) => {
    const parsed = RegisterSchema.safeParse(req.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: "VALIDATION_FAILED", message: "Invalid registration data", details: parsed.error.flatten() });
    }
    try {
      const session = await authService.register(parsed.data, req.headers["user-agent"]);
      setRefreshCookie(reply, session);
      return reply.status(201).send(sessionBody(session));
    } catch (err) {
      return sendError(reply, err);
    }
  });

  server.post("/login", async (req, reply) => {
    const parsed = LoginSchema.safeParse(req.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: "VALIDATION_FAILED", message: "Invalid login data", details: parsed.error.flatten() });
    }
    try {
      const session = await authService.login(parsed.data, req.headers["user-agent"]);
      setRefreshCookie(reply, session);
      return reply.status(200).send(sessionBody(session));
    } catch (err) {
      return sendError(reply, err);
    }
  });

  server.post("/refresh", async (req, reply) => {
    const raw = req.cookies[REFRESH_COOKIE];
    if (!raw) {
      return reply.status(401).send({ error: "MISSING_TOKEN", message: "No refresh token cookie." });
    }
    try {
      const session = await authService.refresh(raw, req.headers["user-agent"]);
      setRefreshCookie(reply, session);
      return reply.status(200).send(sessionBody(session));
    } catch (err) {
      clearRefreshCookie(reply);
      return sendError(reply, err);
    }
  });

  server.post("/logout", async (req, reply) => {
    await authService.logout(req.cookies[REFRESH_COOKIE]);
    clearRefreshCookie(reply);
    return reply.status(204).send();
  });

  server.get("/me", { preHandler: requireAuth }, async (req, reply) => {
    const user = await authService.getUserById(req.user!.sub);
    if (!user) return reply.status(401).send({ error: "INVALID_TOKEN", message: "Account no longer exists." });
    return reply.status(200).send({ user });
  });
};
