/**
 * System Role: JWT issuance and verification — short-lived AccessToken + rotating RefreshToken.
 * Inputs: User identity (id, email, role), raw refresh tokens from the httpOnly cookie, envConfig JWT settings.
 * Outputs: Signed JWT strings; verified access claims; rotated refresh tokens persisted (hashed) in refresh_tokens.
 * Security: HS256 with separate secrets + audiences per token type; refresh rotation with reuse detection
 *           (a revoked token presented after the grace window revokes every session of that user).
 */

import { createHash, randomUUID } from "node:crypto";
import jwt from "jsonwebtoken";
import { envConfig } from "../config/env.config.js";
import { logger } from "../config/logger.js";
import { RefreshTokenModel } from "../models/refresh-token.model.js";
import type { UserRole } from "../models/user.model.js";
import { AuthError } from "../utils/auth-error.js";

const ACCESS_AUDIENCE = "rag-access";
const REFRESH_AUDIENCE = "rag-refresh";

export interface AccessClaims {
  sub: string;
  email: string;
  role: UserRole;
}

export interface IssuedRefreshToken {
  token: string;
  jti: string;
  expiresAt: Date;
}

const sha256 = (value: string) => createHash("sha256").update(value).digest("hex");

export function signAccessToken(claims: AccessClaims): string {
  return jwt.sign({ email: claims.email, role: claims.role }, envConfig.JWT_ACCESS_SECRET, {
    algorithm: "HS256",
    subject: claims.sub,
    issuer: envConfig.JWT_ISSUER,
    audience: ACCESS_AUDIENCE,
    expiresIn: envConfig.JWT_ACCESS_TTL_SECONDS,
  });
}

export function verifyAccessToken(token: string): AccessClaims {
  try {
    const payload = jwt.verify(token, envConfig.JWT_ACCESS_SECRET, {
      algorithms: ["HS256"],
      issuer: envConfig.JWT_ISSUER,
      audience: ACCESS_AUDIENCE,
    }) as jwt.JwtPayload;
    return { sub: String(payload.sub), email: String(payload.email), role: payload.role as UserRole };
  } catch {
    throw new AuthError(401, "INVALID_TOKEN", "Access token is invalid or expired.");
  }
}

export async function issueRefreshToken(
  userId: string,
  userAgent?: string,
  jti: string = randomUUID()
): Promise<IssuedRefreshToken> {
  const token = jwt.sign({}, envConfig.JWT_REFRESH_SECRET, {
    algorithm: "HS256",
    subject: userId,
    jwtid: jti,
    issuer: envConfig.JWT_ISSUER,
    audience: REFRESH_AUDIENCE,
    expiresIn: envConfig.JWT_REFRESH_TTL_SECONDS,
  });
  const expiresAt = new Date(Date.now() + envConfig.JWT_REFRESH_TTL_SECONDS * 1000);

  await RefreshTokenModel.create({
    jti,
    user_id: userId,
    token_hash: sha256(token),
    expires_at: expiresAt,
    user_agent: userAgent?.slice(0, 256),
  });
  return { token, jti, expiresAt };
}

function decodeRefreshToken(token: string): { userId: string; jti: string } {
  try {
    const payload = jwt.verify(token, envConfig.JWT_REFRESH_SECRET, {
      algorithms: ["HS256"],
      issuer: envConfig.JWT_ISSUER,
      audience: REFRESH_AUDIENCE,
    }) as jwt.JwtPayload;
    if (!payload.sub || !payload.jti) throw new Error("missing claims");
    return { userId: payload.sub, jti: payload.jti };
  } catch {
    throw new AuthError(401, "INVALID_TOKEN", "Refresh token is invalid or expired.");
  }
}

export async function revokeAllRefreshTokens(userId: string): Promise<void> {
  await RefreshTokenModel.updateMany({ user_id: userId, revoked_at: null }, { $set: { revoked_at: new Date() } }).exec();
}

/**
 * Exchanges a valid refresh token for a new one (rotation). The old token is revoked atomically,
 * so two concurrent requests cannot both rotate the same token.
 */
export async function rotateRefreshToken(
  token: string,
  userAgent?: string
): Promise<{ userId: string; refresh: IssuedRefreshToken }> {
  const { userId, jti } = decodeRefreshToken(token);
  const newJti = randomUUID();

  const claimed = await RefreshTokenModel.findOneAndUpdate(
    { jti, user_id: userId, token_hash: sha256(token), revoked_at: null },
    { $set: { revoked_at: new Date(), replaced_by: newJti } },
    { new: false }
  ).exec();

  if (!claimed) {
    const existing = await RefreshTokenModel.findOne({ jti }).exec();
    if (existing?.revoked_at) {
      const ageSeconds = (Date.now() - existing.revoked_at.getTime()) / 1000;
      if (ageSeconds > envConfig.REFRESH_REUSE_GRACE_SECONDS) {
        logger.warn(`[TokenService] Refresh token reuse detected for user ${userId} — revoking all sessions.`);
        await revokeAllRefreshTokens(userId);
        throw new AuthError(401, "TOKEN_REUSED", "Refresh token reuse detected. Please log in again.");
      }
    }
    throw new AuthError(401, "INVALID_TOKEN", "Refresh token is no longer valid.");
  }

  const refresh = await issueRefreshToken(userId, userAgent, newJti);
  return { userId, refresh };
}

/** Revokes a single refresh token (logout). Invalid / unknown tokens are ignored. */
export async function revokeRefreshToken(token: string): Promise<void> {
  try {
    const { jti } = decodeRefreshToken(token);
    await RefreshTokenModel.updateOne({ jti, revoked_at: null }, { $set: { revoked_at: new Date() } }).exec();
  } catch {
    // logout must always succeed from the client's point of view
  }
}
