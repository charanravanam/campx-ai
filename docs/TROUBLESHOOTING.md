# Troubleshooting

Never paste passwords, cookies, tokens or `Authorization` headers when asking for help. See `steps_for_chatgpt.md` §12–13.

| Symptom | Cause | Fix |
|---|---|---|
| `scripts\setup.ps1 cannot be loaded… not digitally signed` | PowerShell execution policy | Run `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` |
| `python` / `node` not recognised | Not installed / not on PATH | Reinstall Python (tick "Add to PATH") / Node LTS; reopen PowerShell |
| Login page: "Cannot reach the CampX AI server" | Backend not running or wrong port | Start backend; open http://127.0.0.1:8000/health |
| Vite shows `ECONNREFUSED 127.0.0.1:8000` / proxy error | Backend down | Start the backend first. If it runs elsewhere set `VITE_DEV_BACKEND_URL` in `frontend/.env` |
| **503 `config_missing`** | `APP_SECRET_KEY` empty/short | Run `python scripts\generate_secret.py`, paste into `.env`, restart backend |
| **503 `campx_not_configured`** | `CAMPX_CLIENT_HEADER_VALUE` empty | README "Finding X-Campx-Client" |
| **503 `not_configured`** | Live path for that data isn't set | Set `CAMPX_*_PATH` after DevTools discovery, or import JSON (Settings) |
| **401 `invalid_credentials`** | Wrong ID/password (or CampX 400/401) | Check you can log in on gnitc.campx.in |
| **401 `not_authenticated`** | Session expired / cookie cleared | Sign in again |
| **401 `campx_session_expired`** | CampX token expired or rejected our follow-up auth | Sign in again. If it happens immediately every time, `CAMPX_AUTH_MODE` is probably wrong — DevTools §11 |
| **403 `csrf_failed` / `origin_not_allowed`** | Opened the site via a host not in `FRONTEND_ORIGIN` (e.g. `127.0.0.1` vs `localhost`) or a stale tab | Use `http://localhost:5173`, hard-refresh. Add the origin to `FRONTEND_ORIGIN` (comma separated) |
| **403 `upstream_forbidden`** | CampX said 403: wrong `X-Campx-Client`, blocked account, or wrong auth mode | Re-copy the header value; try other `CAMPX_AUTH_MODE`; ensure the account can use that page in the browser |
| **403 `mfa_unsupported`** | Account requires MFA | Not supported yet. Use `DATA_SOURCE=imported` |
| **404 `upstream_not_found`** | Path wrong | Re-check with DevTools; you may need query parameters (`?x=y`) in the path setting |
| **422 `unsupported_structure`** | Response shape unknown to the normalizer | Make a redacted shape: `python scripts\redact_json.py saved.json` and share only that |
| **429 `too_many_attempts`** | 3–5 failed logins in the window | Wait for `Retry-After`; restart backend clears the in-memory counter |
| **429 `upstream_rate_limited`** | CampX throttling | Wait and retry less often |
| **502 `upstream_unreachable`** | No internet / DNS / proxy blocks `api.campx.in` | Check connectivity; corporate proxy → set `HTTPS_PROXY` env var |
| **502 `campx_auth_not_established`** | CampX gave us no cookies/token for the chosen mode | Change `CAMPX_AUTH_MODE` (`bearer`, `header` + `CAMPX_TOKEN_HEADER`) |
| **502 `upstream_malformed`** | Non-JSON from CampX | Possibly an HTML error/maintenance page; retry later |
| **504 `upstream_timeout`** | Slow CampX | Retry; raise `REQUEST_TIMEOUT_SECONDS` |
| **500 `internal_error`** | Bug | Look at the backend terminal (it logs only the exception type). Share that line, nothing else |
| Backend: `Refusing to start in production` | Production safety check | Fix the listed problems (HTTPS origin, secret length) |
| Cookies not kept after login (production) | Not HTTPS / different domain | Serve frontend and API under the same https site |
| `pip install` fails building `cryptography` | Old Python/pip | `python -m pip install --upgrade pip`, use Python 3.11+ |
| `npm install` errors | Old Node | Install Node 20+ LTS, delete `frontend\node_modules`, retry |
| Port 5173/8000 already in use | Old process still running | Close old terminals, or `netstat -ano | findstr :8000` then `taskkill /PID <pid> /F` |
