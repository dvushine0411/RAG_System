/**
 * System Role: Login / registration screen shown to anonymous visitors.
 * Inputs: Email, name, password from the form; login/register actions from useAuth.
 * Outputs: Calls POST /api/v1/auth/login or /register; shows validation and server errors.
 */

import { useState, type FormEvent } from "react";
import { appConfig } from "../config";
import { useAuth } from "../hooks/useAuth";

type Mode = "login" | "register";

function validatePassword(password: string): string | null {
  if (password.length < appConfig.passwordMinLength) return `Mật khẩu tối thiểu ${appConfig.passwordMinLength} ký tự.`;
  if (new TextEncoder().encode(password).length > appConfig.passwordMaxBytes) return "Mật khẩu quá dài.";
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return "Mật khẩu phải có cả chữ và số.";
  return null;
}

export function AuthPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setPassword("");
    setConfirm("");
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (mode === "register") {
      const problem = validatePassword(password);
      if (problem) return setError(problem);
      if (password !== confirm) return setError("Mật khẩu nhập lại không khớp.");
    }
    setSubmitting(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, name, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>RAG Assistant</h1>
        <div className="auth-tabs" role="tablist">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => switchMode("login")}>
            Đăng nhập
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => switchMode("register")}>
            Đăng ký
          </button>
        </div>

        <label>
          Email
          <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>

        {mode === "register" && (
          <label>
            Họ tên
            <input type="text" autoComplete="name" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}

        <label>
          Mật khẩu
          <input
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {mode === "register" && (
          <>
            <label>
              Nhập lại mật khẩu
              <input type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </label>
            <small className="muted">Tối thiểu {appConfig.passwordMinLength} ký tự, gồm cả chữ và số.</small>
          </>
        )}

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={submitting}>
          {submitting ? "Đang xử lý…" : mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
        </button>
      </form>
    </div>
  );
}
