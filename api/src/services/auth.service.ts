/**
 * System Role: Authentication use-cases — register, login, refresh (rotation), logout, admin bootstrap.
 * Inputs: Validated credentials from auth.route.ts, raw refresh tokens, envConfig.ADMIN_* for seeding.
 * Outputs: AuthSession { user, accessToken, refresh } or AuthError (409 / 401).
 * Flow: auth.route.ts -> auth.service.ts -> password.service.ts (bcrypt) / token.service.ts (JWT) -> MongoDB
 */

import { randomUUID } from "node:crypto";
import { envConfig } from "../config/env.config.js";
import { logger } from "../config/logger.js";
import { IUser, PublicUser, toPublicUser, UserModel, UserRole } from "../models/user.model.js";
import { AuthError } from "../utils/auth-error.js";
import { hashPassword, verifyPassword } from "./password.service.js";
import {
  IssuedRefreshToken,
  issueRefreshToken,
  revokeRefreshToken,
  rotateRefreshToken,
  signAccessToken,
} from "./token.service.js";

export interface AuthSession {
  user: PublicUser;
  accessToken: string;
  refresh: IssuedRefreshToken;
}

const DUPLICATE_KEY_ERROR = 11000;

async function startSession(user: IUser, userAgent?: string): Promise<AuthSession> {
  const accessToken = signAccessToken({ sub: user.id, email: user.email, role: user.role });
  const refresh = await issueRefreshToken(user.id, userAgent);
  return { user: toPublicUser(user), accessToken, refresh };
}

async function createUser(email: string, name: string, password: string, role: UserRole): Promise<IUser> {
  const password_hash = await hashPassword(password);
  try {
    return await UserModel.create({ id: randomUUID(), email, name, password_hash, role });
  } catch (err: unknown) {
    if ((err as { code?: number }).code === DUPLICATE_KEY_ERROR) {
      throw new AuthError(409, "EMAIL_TAKEN", "An account with this email already exists.");
    }
    throw err;
  }
}

export async function register(
  input: { email: string; name: string; password: string },
  userAgent?: string
): Promise<AuthSession> {
  const email = input.email.toLowerCase();
  if (await UserModel.exists({ email })) {
    throw new AuthError(409, "EMAIL_TAKEN", "An account with this email already exists.");
  }
  // Self-registration always creates a regular user; admins come from ensureAdminAccount().
  const user = await createUser(email, input.name, input.password, "user");
  logger.info(`[AuthService] Registered user ${user.id}`);
  return startSession(user, userAgent);
}

export async function login(input: { email: string; password: string }, userAgent?: string): Promise<AuthSession> {
  const user = (await UserModel.findOne({ email: input.email.toLowerCase() }).exec()) as IUser | null;
  // verifyPassword runs bcrypt even when the user is missing, so timing does not reveal valid emails.
  const valid = await verifyPassword(input.password, user?.password_hash);
  if (!user || !valid) {
    throw new AuthError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.");
  }
  user.last_login_at = new Date();
  await user.save();
  return startSession(user, userAgent);
}

export async function refresh(rawRefreshToken: string, userAgent?: string): Promise<AuthSession> {
  const { userId, refresh: rotated } = await rotateRefreshToken(rawRefreshToken, userAgent);
  const user = (await UserModel.findOne({ id: userId }).exec()) as IUser | null;
  if (!user) throw new AuthError(401, "INVALID_TOKEN", "Account no longer exists.");
  const accessToken = signAccessToken({ sub: user.id, email: user.email, role: user.role });
  return { user: toPublicUser(user), accessToken, refresh: rotated };
}

export async function logout(rawRefreshToken: string | undefined): Promise<void> {
  if (rawRefreshToken) await revokeRefreshToken(rawRefreshToken);
}

export async function getUserById(id: string): Promise<PublicUser | null> {
  const user = (await UserModel.findOne({ id }).exec()) as IUser | null;
  return user ? toPublicUser(user) : null;
}

/** Creates (or promotes) the bootstrap admin from ADMIN_EMAIL / ADMIN_PASSWORD, if configured. */
export async function ensureAdminAccount(): Promise<void> {
  if (!envConfig.ADMIN_EMAIL || !envConfig.ADMIN_PASSWORD) {
    logger.warn("[AuthService] ADMIN_EMAIL / ADMIN_PASSWORD not set — no admin account bootstrapped.");
    return;
  }
  const email = envConfig.ADMIN_EMAIL.toLowerCase();
  const existing = (await UserModel.findOne({ email }).exec()) as IUser | null;
  if (!existing) {
    await createUser(email, "Administrator", envConfig.ADMIN_PASSWORD, "admin");
    logger.info(`[AuthService] Bootstrap admin '${email}' created.`);
  } else if (existing.role !== "admin") {
    existing.role = "admin";
    await existing.save();
    logger.info(`[AuthService] Existing account '${email}' promoted to admin.`);
  }
}
