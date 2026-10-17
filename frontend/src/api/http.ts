/**
 * System Role: Fetch wrapper for the API Gateway — builds /api/v1 URLs, attaches the Bearer access token,
 *              transparently refreshes it once on 401, and normalizes error responses.
 * Inputs: Path under /api/v1, fetch RequestInit (+ `auth: false` to skip token handling).
 * Outputs: Successful Response, or a thrown ApiError carrying status and the gateway's message.
 */

import { appConfig } from "../config";
import { getAccessToken, notifySessionExpired, setAccessToken } from "../lib/token-store";
import type { AuthSessionResponse } from "../types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string
  ) {
    super(message);
  }
}

export function apiUrl(path: string): string {
  return `${appConfig.apiBaseUrl}/api/v1${path}`;
}

async function toApiError(res: Response): Promise<ApiError> {
  let message = `${res.status} ${res.statusText}`;
  let code: string | undefined;
  try {
    const body = await res.json();
    message = body.message ?? body.error ?? message;
    code = body.error;
  } catch {
    // non-JSON error body: keep status text
  }
  return new ApiError(res.status, message, code);
}

// Single-flight: concurrent 401s (or React StrictMode double effects) share one refresh request,
// so a rotated refresh token is never presented twice.
let refreshInFlight: Promise<AuthSessionResponse> | null = null;

export function refreshSession(): Promise<AuthSessionResponse> {
  refreshInFlight ??= (async () => {
    try {
      const res = await fetch(apiUrl("/auth/refresh"), { method: "POST", credentials: "include" });
      if (!res.ok) throw await toApiError(res);
      const session = (await res.json()) as AuthSessionResponse;
      setAccessToken(session.access_token);
      return session;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export interface ApiFetchInit extends RequestInit {
  /** false = do not attach/refresh the access token (login, register, refresh, logout). */
  auth?: boolean;
}

export async function apiFetch(path: string, init: ApiFetchInit = {}): Promise<Response> {
  const { auth = true, ...requestInit } = init;

  const send = () => {
    const headers = new Headers(requestInit.headers);
    const token = getAccessToken();
    if (auth && token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(apiUrl(path), { credentials: "include", ...requestInit, headers });
  };

  let res = await send();
  if (res.status === 401 && auth) {
    try {
      await refreshSession();
    } catch {
      notifySessionExpired();
      throw new ApiError(401, "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", "SESSION_EXPIRED");
    }
    res = await send();
  }

  if (!res.ok) throw await toApiError(res);
  return res;
}
