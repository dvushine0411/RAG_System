/**
 * System Role: Authentication context — restores the session on page load via the refresh cookie,
 *              exposes the current user and login / register / logout actions to the component tree.
 * Inputs: User actions from AuthPage / UserBar; session-expired events from api/http.ts.
 * Outputs: AuthContext { status, user, login, register, logout }.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as authApi from "../api/auth.api";
import { refreshSession } from "../api/http";
import { onSessionExpired } from "../lib/token-store";
import type { AuthUser } from "../types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, name: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);

  const signedIn = (u: AuthUser) => {
    setUser(u);
    setStatus("authenticated");
  };
  const signedOut = useCallback(() => {
    setUser(null);
    setStatus("anonymous");
  }, []);

  // Restore session from the httpOnly refresh cookie (single-flight inside refreshSession).
  useEffect(() => {
    let cancelled = false;
    refreshSession()
      .then((session) => !cancelled && signedIn(session.user))
      .catch(() => !cancelled && signedOut());
    return () => {
      cancelled = true;
    };
  }, [signedOut]);

  useEffect(() => onSessionExpired(signedOut), [signedOut]);

  const login = useCallback(async (email: string, password: string) => {
    signedIn((await authApi.login(email, password)).user);
  }, []);

  const register = useCallback(async (email: string, name: string, password: string) => {
    signedIn((await authApi.register(email, name, password)).user);
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout().catch(() => undefined);
    signedOut();
  }, [signedOut]);

  const value = useMemo(() => ({ status, user, login, register, logout }), [status, user, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
