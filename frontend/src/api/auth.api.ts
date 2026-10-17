/**
 * System Role: Client for authentication endpoints (register, login, logout, current user).
 * Inputs: Credentials from AuthPage via useAuth.
 * Outputs: AuthSessionResponse (access token is stored in memory by these calls) / AuthUser.
 * Endpoints: POST /api/v1/auth/register | login | logout, GET /api/v1/auth/me
 */

import { apiFetch } from "./http";
import { setAccessToken } from "../lib/token-store";
import type { AuthSessionResponse, AuthUser } from "../types";

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

async function startSession(res: Response): Promise<AuthSessionResponse> {
  const session = (await res.json()) as AuthSessionResponse;
  setAccessToken(session.access_token);
  return session;
}

export async function register(email: string, name: string, password: string): Promise<AuthSessionResponse> {
  return startSession(await apiFetch("/auth/register", { ...json({ email, name, password }), auth: false }));
}

export async function login(email: string, password: string): Promise<AuthSessionResponse> {
  return startSession(await apiFetch("/auth/login", { ...json({ email, password }), auth: false }));
}

export async function logout(): Promise<void> {
  try {
    await apiFetch("/auth/logout", { method: "POST", auth: false });
  } finally {
    setAccessToken(null);
  }
}

export async function fetchMe(): Promise<AuthUser> {
  const res = await apiFetch("/auth/me");
  return ((await res.json()) as { user: AuthUser }).user;
}
