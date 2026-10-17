/**
 * System Role: Fastify preHandler guards enforcing JWT authentication and role-based authorization.
 * Inputs: `Authorization: Bearer <accessToken>` header.
 * Outputs: request.user = { sub, email, role } on success; 401 (missing/invalid token) or 403 (wrong role).
 */

import type { FastifyReply, FastifyRequest, preHandlerAsyncHookHandler } from "fastify";
import type { UserRole } from "../models/user.model.js";
import { AccessClaims, verifyAccessToken } from "../services/token.service.js";
import { AuthError } from "../utils/auth-error.js";

declare module "fastify" {
  interface FastifyRequest {
    user?: AccessClaims;
  }
}

function sendAuthError(reply: FastifyReply, err: AuthError) {
  return reply.status(err.statusCode).send({ error: err.code, message: err.message });
}

export const requireAuth: preHandlerAsyncHookHandler = async (request: FastifyRequest, reply: FastifyReply) => {
  const header = request.headers.authorization;
  if (!header?.startsWith("Bearer ")) {
    return sendAuthError(reply, new AuthError(401, "MISSING_TOKEN", "Authorization Bearer token is required."));
  }
  try {
    request.user = verifyAccessToken(header.slice(7).trim());
  } catch (err) {
    return sendAuthError(reply, err as AuthError);
  }
};

export function requireRole(...roles: UserRole[]): preHandlerAsyncHookHandler {
  return async (request: FastifyRequest, reply: FastifyReply) => {
    if (!request.user) {
      return sendAuthError(reply, new AuthError(401, "MISSING_TOKEN", "Authentication required."));
    }
    if (!roles.includes(request.user.role)) {
      return sendAuthError(reply, new AuthError(403, "FORBIDDEN", `Requires role: ${roles.join(" or ")}.`));
    }
  };
}
