/**
 * System Role: Typed error carrying an HTTP status and machine-readable code for auth failures.
 * Inputs: status code, error code, human-readable message.
 * Outputs: AuthError instances that auth.route.ts / auth.middleware.ts map to JSON responses.
 */

export type AuthErrorCode =
  | "EMAIL_TAKEN"
  | "INVALID_CREDENTIALS"
  | "MISSING_TOKEN"
  | "INVALID_TOKEN"
  | "TOKEN_REUSED"
  | "FORBIDDEN";

export class AuthError extends Error {
  constructor(
    public readonly statusCode: number,
    public readonly code: AuthErrorCode,
    message: string
  ) {
    super(message);
    this.name = "AuthError";
  }
}
