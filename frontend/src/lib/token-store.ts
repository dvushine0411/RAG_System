/**
 * System Role: In-memory holder for the JWT access token (never persisted — mitigates XSS token theft).
 * Inputs: Access tokens from login / register / refresh responses.
 * Outputs: getAccessToken(); "session expired" notifications for AuthProvider.
 * Note: the refresh token lives only in an httpOnly cookie that JavaScript cannot read.
 */

let accessToken: string | null = null;
const expiredListeners = new Set<() => void>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function onSessionExpired(listener: () => void): () => void {
  expiredListeners.add(listener);
  return () => expiredListeners.delete(listener);
}

export function notifySessionExpired(): void {
  accessToken = null;
  expiredListeners.forEach((l) => l());
}
