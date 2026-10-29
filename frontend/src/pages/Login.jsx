import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

const MESSAGES = {
  invalid_credentials: "That login ID or password is not correct.",
  too_many_attempts: "Too many attempts. Please wait before trying again.",
  upstream_rate_limited: "CampX is limiting sign-ins right now. Please wait a few minutes.",
  upstream_unavailable: "CampX is having problems. Try again in a little while.",
  upstream_unreachable: "Could not reach CampX. Check your internet connection.",
  upstream_timeout: "CampX took too long to answer. Try again.",
  mfa_unsupported: "Your CampX account asks for multi-factor verification. CampX AI cannot complete that step yet, so you were not signed in.",
  campx_not_configured: "The server is missing CAMPX_CLIENT_HEADER_VALUE. Ask the person running CampX AI to follow the README.",
  config_missing: "The server is not configured yet (APP_SECRET_KEY). Follow the README setup.",
  network: "Cannot reach the CampX AI server. Is the backend running on port 8000?",
};

export default function Login() {
  const { login, bootError } = useAuth();
  const nav = useNavigate();
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(bootError ? (MESSAGES[bootError.code] || bootError.message) : null);

  async function submit(e) {
    e.preventDefault();
    const v = {};
    if (loginId.trim().length < 3) v.loginId = "Enter your CampX email or login ID.";
    if (!password) v.password = "Enter your password.";
    setErrors(v);
    setFormError(null);
    if (Object.keys(v).length) return;
    setBusy(true);
    try {
      await login(loginId.trim(), password);
      setPassword("");
      nav("/", { replace: true });
    } catch (err) {
      const wait = err.retryAfter ? ` Try again in about ${Math.ceil(err.retryAfter / 60)} min.` : "";
      setFormError((MESSAGES[err.code] || err.message) + (err.code === "too_many_attempts" ? wait : ""));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <section className="login-panel">
        <div className="brand brand-lg"><span className="mark" aria-hidden="true">C</span> CampX AI</div>
        <h1>Your GNITC week, in one place</h1>
        <p className="muted">Sign in with your CampX account. Your password goes straight to CampX and is never saved by this app.</p>
        <form onSubmit={submit} noValidate autoComplete="on">
          {formError && <div className="notice notice-error" role="alert">{formError}</div>}
          <label htmlFor="loginId">Email or login ID</label>
          <input id="loginId" name="username" type="text" inputMode="email" autoComplete="username" autoCapitalize="none" spellCheck="false"
            value={loginId} onChange={(e) => setLoginId(e.target.value)} aria-invalid={!!errors.loginId} aria-describedby={errors.loginId ? "e-login" : undefined} />
          {errors.loginId && <p id="e-login" className="field-error">{errors.loginId}</p>}

          <label htmlFor="password">Password</label>
          <div className="pw">
            <input id="password" name="password" type={show ? "text" : "password"} autoComplete="current-password"
              value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={!!errors.password} aria-describedby={errors.password ? "e-pw" : undefined} />
            <button type="button" className="btn-quiet pw-toggle" onClick={() => setShow((s) => !s)} aria-pressed={show}>{show ? "Hide" : "Show"}</button>
          </div>
          {errors.password && <p id="e-pw" className="field-error">{errors.password}</p>}

          <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
      </section>
    </div>
  );
}
