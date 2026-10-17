/**
 * System Role: Password hashing and verification with bcrypt (bcryptjs, pure JS — no native build).
 * Inputs: Plain-text password; cost factor from envConfig.BCRYPT_COST.
 * Outputs: bcrypt hash string ("$2a$<cost>$<salt+hash>") / boolean match result.
 * Note: bcrypt only uses the first 72 bytes of input — auth.route.ts rejects longer passwords.
 */

import bcrypt from "bcryptjs";
import { envConfig } from "../config/env.config.js";

export const BCRYPT_MAX_PASSWORD_BYTES = 72;

// Pre-computed hash of a random string: compared against when the email is unknown so that
// login takes the same time whether or not the account exists (prevents user enumeration).
const DUMMY_HASH = bcrypt.hashSync("dummy-password-for-timing-equalization", envConfig.BCRYPT_COST);

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, envConfig.BCRYPT_COST);
}

export async function verifyPassword(password: string, hash: string | null | undefined): Promise<boolean> {
  const matched = await bcrypt.compare(password, hash ?? DUMMY_HASH);
  return Boolean(hash) && matched;
}
