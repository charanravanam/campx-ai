// All HTTP calls live here. Credentials/tokens are never stored by this file:
// the session lives in an HttpOnly cookie the browser manages; the CSRF token
// is kept in memory only.
let csrfToken = null;
let onUnauthorized = () => {};

export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

export class ApiError extends Error {
  constructor(status, code, message, extra = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryAfter = extra.retryAfter;
    this.fields = extra.fields;
  }
}

async function ensureCsrf(force = false) {
  if (csrfToken && !force) return csrfToken;
  const res = await fetch("/api/auth/csrf", { credentials: "same-origin" });
  if (!res.ok) throw await toError(res);
  csrfToken = (await res.json()).csrf_token;
  return csrfToken;
}

async function toError(res) {
  let body = null;
  try { body = await res.json(); } catch { /* not JSON */ }
  const e = body?.error;
  return new ApiError(
    res.status,
    e?.code || "http_error",
    e?.message || `Request failed (HTTP ${res.status}).`,
    { retryAfter: Number(res.headers.get("retry-after")) || undefined, fields: e?.fields },
  );
}

async function request(method, path, { json, rawBody, signal } = {}, retried = false) {
  const headers = {};
  const unsafe = method !== "GET";
  if (unsafe) headers["X-CSRF-Token"] = await ensureCsrf();
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (rawBody !== undefined) { headers["Content-Type"] = "application/json"; body = rawBody; }
  let res;
  try {
    res = await fetch(path, { method, headers, body, credentials: "same-origin", signal });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError(0, "network", "Cannot reach the CampX AI server. Is the backend running?");
  }
  if (!res.ok) {
    const err = await toError(res);
    if (err.code === "csrf_failed" && !retried) {
      await ensureCsrf(true);
      return request(method, path, { json, rawBody, signal }, true);
    }
    if (err.status === 401 && path !== "/api/auth/login") onUnauthorized(err);
    throw err;
  }
  return res.json();
}

export const api = {
  me: () => request("GET", "/api/auth/me"),
  login: async (loginId, password) => {
    const out = await request("POST", "/api/auth/login", { json: { loginId, password } });
    csrfToken = out.csrf_token; // rotated by the server on login
    return out;
  },
  logout: async () => { const o = await request("POST", "/api/auth/logout"); csrfToken = null; return o; },
  profile: (signal) => request("GET", "/api/profile", { signal }),
  timetable: (signal) => request("GET", "/api/timetable", { signal }),
  today: (signal) => request("GET", "/api/timetable/today", { signal }),
  attendance: (target, signal) => request("GET", `/api/attendance?target=${encodeURIComponent(target)}`, { signal }),
  forecast: (target, labUnits, signal) => request("GET", `/api/attendance/forecast?target=${encodeURIComponent(target)}&lab_units=${labUnits}`, { signal }),
  setAdjustment: (subject_key, session_key, status) => request("POST", "/api/attendance/adjustments", { json: { subject_key, session_key, status } }),
  resetAdjustments: (subjectKey) => request("DELETE", `/api/attendance/adjustments${subjectKey ? `?subject_key=${encodeURIComponent(subjectKey)}` : ""}`),
  clearSession: (sessionKey) => request("DELETE", `/api/attendance/adjustments?session_key=${encodeURIComponent(sessionKey)}`),
  scenario: (body, labUnits, signal) => request("POST", `/api/attendance/scenario?lab_units=${labUnits}`, { json: body, signal }),
  subjects: (signal) => request("GET", "/api/subjects", { signal }),
  importStatus: () => request("GET", "/api/import/status"),
  importJson: (kind, text) => request("POST", `/api/import/${kind}`, { rawBody: text }),
  deleteImport: (kind) => request("DELETE", `/api/import/${kind}`),
};
