/**
 * System Role: Centralized frontend configuration — the only module allowed to read import.meta.env.
 * Inputs: VITE_API_BASE_URL (build-time env, optional).
 * Outputs: appConfig with API base URL and UI tunables.
 */

export const appConfig = {
  /** Prefix for /api/v1/* calls. Empty string = same origin (Nginx / Vite proxy). */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, ""),
  /** Number of previous chat turns sent as conversation_history. */
  historyTurns: 6,
  /** Accepted upload extensions (must match api/src/utils/source-type.ts). */
  acceptedExtensions: [".pdf", ".docx", ".doc", ".md", ".markdown", ".txt", ".html", ".htm"],
  /** Password rules (must match api/src/routes/auth.route.ts PasswordSchema; bcrypt reads max 72 bytes). */
  passwordMinLength: 8,
  passwordMaxBytes: 72,
} as const;
