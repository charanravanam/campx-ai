# CampX AI — Handoff guide for ChatGPT (and for you)

This file lets a fresh ChatGPT conversation guide a beginner from zero to a working CampX AI app, one step at a time. **Paste this whole file into ChatGPT** at the start of a new chat, then say: *"Follow the 'Instructions for ChatGPT' section and start at step 1."*

---

## 0. Instructions for ChatGPT

You are helping a beginner on **Windows PowerShell** run and extend the CampX AI project described below. Follow these rules:

1. **One step at a time.** Give one small step, ask the user to run it, and wait for the output. Never dump 15 steps at once.
2. **Ask the user to run commands and paste the output.** Prefer outputs like `python --version`, `curl.exe http://127.0.0.1:8000/health`, test summaries, and the *last 20 lines* of an error.
3. **Never ask for secrets.** Do not ask for passwords, cookies, session tokens, `Authorization` headers, the `.env` file contents, `campx_session_key`, or screenshots showing them. If the user pastes one, tell them to treat it as compromised and rotate it (SECURITY.md, "If something leaked").
4. **Inspect before replacing.** Before changing any file, ask the user to show it (`Get-Content path\to\file`) or the relevant part. Edit the smallest necessary part; never regenerate whole files blindly. Keep names consistent with the structure in section 1.
5. **Never assume an unverified API route works.** `CAMPX_TIMETABLE_PATH=/student-api/classroom-timetables` was only *observed*. Attendance, profile and subjects routes are *unknown*. Use the DevTools procedure (section 11) and a redacted sample (section 12) before writing code that depends on them.
6. **Never bypass security.** Do not disable authentication, CSRF, CORS, rate limits, MFA or CAPTCHA to "fix" `401`/`403`/`503`. Diagnose the cause instead.
7. **Never invent** header values, endpoints, response fields, attendance numbers or timetable data. If something is unknown, say so and use the safe config point or JSON import.
8. **Be honest about status.** Use the checklist in section 15. Do not say a feature "works" unless the user ran it and showed you the result.
9. After each code change, have the user run the tests (section 14) and report the summary line.
10. Keep explanations short and plain. Explain what a command does before asking the user to run it.

---

## 1. Project directory structure

```
campx-ai/
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── admin.py
│   │   │   ├── auth.py
│   │   │   ├── data.py
│   │   │   └── imports.py
│   │   ├── __init__.py
│   │   ├── calculations.py
│   │   ├── campx_client.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── db_init.py
│   │   ├── deps.py
│   │   ├── errors.py
│   │   ├── main.py
│   │   ├── normalizers.py
│   │   ├── ratelimit.py
│   │   ├── schemas.py
│   │   ├── security.py
│   │   ├── services.py
│   │   ├── sessions.py
│   │   └── timetable_logic.py
│   ├── sample_data/
│   │   ├── sample_attendance.json
│   │   ├── sample_profile.json
│   │   ├── sample_subjects.json
│   │   ├── sample_timetable.json
│   │   └── sample_timetable_weekday_keyed.json
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_calculations.py
│   │   ├── test_data.py
│   │   ├── test_normalizers.py
│   │   └── test_security.py
│   ├── pytest.ini
│   └── requirements.txt
├── docs/
│   ├── API.md
│   └── TROUBLESHOOTING.md
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Layout.jsx
│   │   │   └── ui.jsx
│   │   ├── pages/
│   │   │   ├── Attendance.jsx
│   │   │   ├── Login.jsx
│   │   │   ├── Overview.jsx
│   │   │   ├── Profile.jsx
│   │   │   ├── Settings.jsx
│   │   │   ├── Subjects.jsx
│   │   │   └── Timetable.jsx
│   │   ├── App.jsx
│   │   ├── api.js
│   │   ├── auth.jsx
│   │   ├── hooks.js
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── .env.example
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── generate_secret.py
│   ├── redact_json.py
│   ├── run-tests.ps1
│   ├── setup.ps1
│   ├── start-all.ps1
│   ├── start-backend.ps1
│   └── start-frontend.ps1
├── .env.example
├── .gitignore
├── BUILD_REPORT.md
├── README.md
├── SECURITY.md
└── steps_for_chatgpt.md
```

## 2. What each important file does

| File | Purpose |
|---|---|
| `.env.example` | Template of all settings (placeholders only). Copy to `.env`. |
| `.env` | **Your real local config. Secret. Never share/commit.** |
| `scripts/setup.ps1` | One-time install: venv, Python deps, `.env` with random secret, npm install |
| `scripts/start-*.ps1` | Start backend / frontend / both |
| `scripts/run-tests.ps1` | Backend tests + frontend build |
| `scripts/generate_secret.py` | Prints a random secret |
| `scripts/redact_json.py` | Turns a saved JSON response into a **values-removed shape** that is safe to share |
| `backend/app/main.py` | Creates the FastAPI app: CORS, CSRF/origin guard, security headers, `/health`, routers |
| `backend/app/config.py` | All settings (names = `.env` names) and production safety checks |
| `backend/app/campx_client.py` | The **only** code that calls CampX: login + authenticated GET |
| `backend/app/sessions.py` | Per-student website sessions in SQLite; encrypted CampX state |
| `backend/app/security.py` | Encryption, CSRF tokens, session-id hashing, origin check |
| `backend/app/ratelimit.py` | Login attempt limiter |
| `backend/app/normalizers.py` | Converts live/imported JSON to fixed shapes; rejects unknown shapes |
| `backend/app/calculations.py` | Attendance maths |
| `backend/app/timetable_logic.py` | Today / current / next class |
| `backend/app/services.py` | Chooses live vs imported per `DATA_SOURCE`; import storage |
| `backend/app/routes/*.py` | `auth`, `data`, `imports`, `admin` endpoints |
| `backend/app/errors.py` | One error format; never echoes passwords |
| `backend/sample_data/*.json` | **Fake** sample data for testing/importing |
| `backend/tests/` | Automated tests with a fake CampX (no network) |
| `frontend/vite.config.js` | Dev server + `/api` proxy to the backend |
| `frontend/src/api.js` | All fetch calls, CSRF handling (token kept in memory only) |
| `frontend/src/pages/*.jsx` | Login, Overview, Profile, Timetable, Attendance, Subjects, Settings |

## 3. Prerequisites (Windows PowerShell)

```powershell
python --version      # needs 3.11 or newer
node --version        # needs 20 or newer
npm --version
```
If missing: Python from https://www.python.org/downloads/ (**tick "Add python.exe to PATH"**), Node LTS from https://nodejs.org/. Close and reopen PowerShell afterwards.

Unzip `campx-ai-complete.zip`, then:
```powershell
cd C:\path\to\campx-ai
```

## 4. Python virtual environment (manual way)

`scripts\setup.ps1` does this for you (`powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`). Manually:
```powershell
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1     # prompt now starts with (.venv)
```
If activation is blocked: `Set-ExecutionPolicy -Scope Process Bypass` then retry.

## 5. Install backend dependencies

```powershell
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## 6. Install frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

## 7. Configure `.env` safely

```powershell
Copy-Item .env.example .env
backend\.venv\Scripts\python.exe scripts\generate_secret.py     # prints a random string
notepad .env
```
In Notepad: paste the string after `APP_SECRET_KEY=`; later set `CAMPX_CLIENT_HEADER_VALUE=` (section 11A). **Do not put your CampX email or password in `.env`** — you type them on the login page. Never share `.env`.

## 8. Start backend and frontend (two terminals)

Terminal 1:
```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Terminal 2:
```powershell
cd frontend
npm run dev
```
Or both at once: `powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1`.

## 9. URLs and health checks

| What | URL |
|---|---|
| App | http://localhost:5173 (the default `FRONTEND_ORIGIN` allows both `localhost` and `127.0.0.1`) |
| Backend health | http://127.0.0.1:8000/health |
| API docs (dev only) | http://127.0.0.1:8000/docs |

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://localhost:5173/health      # same answer = the Vite proxy works
```
Expect `"status":"ok"` and `"secret_key_ok":true`. If `login` under `live_endpoints_configured` is `false`, `CAMPX_CLIENT_HEADER_VALUE` is still empty.

## 10. Verify each feature

All data endpoints require a login, so first complete section 11A and sign in.

1. **Login:** sign in at http://localhost:5173. Success → Overview. Failure shows a specific message (wrong password, rate limited, MFA unsupported, CampX down). Nothing is reported as success unless CampX returned a session.
2. **Imports (works even if live routes are unknown):** Settings → Import: choose the fake files in `backend\sample_data\` (`sample_timetable.json`, `sample_attendance.json`, `sample_profile.json`, `sample_subjects.json`). Pages then show an amber **Imported JSON** badge (in `auto` mode this happens when the live route is not configured/found).
3. **Profile:** Profile page. Empty until `CAMPX_PROFILE_PATH` is set (or a profile is imported). That is expected.
4. **Timetable:** with `CAMPX_TIMETABLE_PATH` set, the page shows the green **Live CampX** badge *if* the route works and the shape is recognised; otherwise you get a precise error (`404`, `403`, `422 unsupported_structure`…) or the imported fallback.
5. **Attendance:** needs `CAMPX_ATTENDANCE_PATH` (unknown) or an import. No numbers are ever invented.
6. **Logout:** Settings → Log out. The login page appears and `curl.exe http://127.0.0.1:8000/api/auth/me` answers 401.

To see imported data only, set `DATA_SOURCE=imported` in `.env` and restart the backend.

## 11. Discovering the real CampX requests with Chrome DevTools

### 11A. The `X-Campx-Client` header (needed for login)
1. Open https://gnitc.campx.in in Chrome → press **F12** → **Network** → tick **Preserve log** → filter **Fetch/XHR**.
2. Log in normally. Click the `login` request.
3. **Headers → Request Headers → `X-Campx-Client`** → copy only that value into `.env` as `CAMPX_CLIENT_HEADER_VALUE=`.
4. Do not copy `Cookie`, do not use "Copy as cURL" (it includes cookies), do not screenshot with a password visible.
5. If you believe the value is a private key meant only for you, or CampX's terms forbid this use, stop and use JSON import.

### 11B. Timetable request
1. Stay logged in, open the **Timetable** page in CampX with the Network tab recording.
2. Click the request that returns your timetable (likely `classroom-timetables`).
3. Write down (these are safe): **Method**, **the URL path + query string** (e.g. `/student-api/classroom-timetables?x=y`), and **which request header *names*** exist (`Authorization`? `Cookie`? anything custom?) — names only, never values.
4. Put the path (with query string) into `CAMPX_TIMETABLE_PATH`.
5. **Which auth mode?** If the request has an `Authorization: Bearer …` header → `CAMPX_AUTH_MODE=bearer`. If it only has `Cookie` → `cookie` (default). If a custom header carries the token → `CAMPX_AUTH_MODE=header` + `CAMPX_TOKEN_HEADER=<that header name>`. You can combine: `cookie,bearer`. Restart the backend after changes.
6. To share the response *shape*: **Response** tab → right-click → *Copy response* → paste into a file `saved.json` → run
   `backend\.venv\Scripts\python.exe scripts\redact_json.py saved.json`
   → read the output (it keeps keys but replaces all values) → share that.

### 11C. Attendance (and profile / subjects)
Repeat 11B on the CampX Attendance page (and profile page). Put the path in `CAMPX_ATTENDANCE_PATH` (`CAMPX_PROFILE_PATH`, `CAMPX_SUBJECTS_PATH`). If the shape is unknown you get `422 unsupported_structure`; share the redacted shape and extend `backend/app/normalizers.py` + a test.

## 12. What is safe to share with ChatGPT

* Command output of `--version`, `/health` (it contains no secrets), `pytest` summary lines.
* Error **codes and messages** from the app (`upstream_not_found`, …) and the last 20 lines of the backend terminal.
* DevTools: request **method**, **URL path/query**, request header **names**, response **status code**, and a **redacted shape** from `scripts\redact_json.py` after you've read it.
* File contents of code files you edited (not `.env`).
* `.env` with every value deleted except non-secret ones (e.g. `DATA_SOURCE=auto`).

## 13. What must NEVER be shared

Passwords · `Cookie` / `Set-Cookie` values (`campx_session_key`, `campx_tenant`, `campx_institution`, our `campxai_session`) · session tokens · `Authorization` headers · `APP_SECRET_KEY` · `ADMIN_TOKEN` · "Copy as cURL" output · HAR files · real student records (names, roll numbers, marks, attendance) · screenshots containing any of these. If shared by mistake → SECURITY.md → "If something leaked".

## 14. Running the tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```
Report just the final line (e.g. `N passed`). Tests use a fake CampX; no internet or credentials needed.

## 15. Implementation status checklist

Legend: **Tested** = automated test passes against a *mock* CampX. **Unverified** = written but never run against the real CampX. **Awaiting config** = needs a value from you.

| Feature | Status |
|---|---|
| FastAPI app, `/health`, `/docs` | Implemented, tested; also started with uvicorn and probed with curl in the build sandbox |
| Per-user sessions (SQLite, encrypted upstream state, expiry, logout) | Implemented, tested |
| Session cookie HttpOnly/SameSite, `Secure` in production | Implemented, tested (cookie attributes); real HTTPS unverified |
| CSRF + origin validation, CORS allow-list | Implemented, tested |
| Login rate limiting (account + IP) | Implemented, tested (in-memory) |
| CampX login request (observed shape/headers) | Implemented, tested vs mock; **Unverified vs real CampX** |
| `X-Campx-Client` value | **Awaiting config** (you, section 11A) |
| MFA | Not supported: refused with clear message (tested vs mock) |
| Follow-up auth to CampX (`CAMPX_AUTH_MODE`) | Implemented (cookie/bearer/header); tested cookie+bearer vs mock; **Unverified** which mode CampX needs |
| Live timetable `/student-api/classroom-timetables` | Implemented, tested vs mock; **Unverified** route, params and shape |
| Live profile / attendance / subjects | Code ready; **Awaiting config** (routes unknown) |
| Re-authentication on expiry | Not possible by design (no stored password): user signs in again |
| Normalizers (timetable/profile/attendance/subjects) | Implemented, tested on synthetic shapes; **aliases unverified vs real CampX** |
| Attendance maths (+ brute-force verification) | Implemented, tested |
| Import endpoints (size limit, validation, per-user isolation) | Implemented, tested |
| Data-source modes `campx`/`imported`/`auto` | Implemented, tested |
| Admin endpoints (separate token) | Implemented, tested |
| React app: 7 pages, loading/empty/error states | Implemented; `npm run build` passes; **not exercised in a real browser** |
| PowerShell scripts | Written; **not executed** (no Windows/PowerShell in the build environment) |
| Frontend automated tests | Not implemented |
| Production HTTPS deployment | Documented; **unverified** |

## 16. Known limitations

No MFA · not tested with real CampX · re-login needed after CampX session expiry · limiter is per-process · profile photos behind CampX auth won't load · alias-based normalizers may need extension once real payloads are seen · SQLite is single-server · subjects are derived from timetable/attendance unless a subjects route/import exists.

## 17. Common errors and fixes

Full table: `docs/TROUBLESHOOTING.md`. The big ones:

| Code | Meaning → first thing to check |
|---|---|
| **401** `not_authenticated` / `campx_session_expired` | Sign in again. Repeats instantly → wrong `CAMPX_AUTH_MODE` |
| **403** `csrf_failed` / `origin_not_allowed` | Use http://localhost:5173; match `FRONTEND_ORIGIN` |
| **403** `upstream_forbidden` | CampX refused: re-check `X-Campx-Client`, auth mode, account access |
| **429** | Wait (`Retry-After`); don't hammer login |
| **500** | Read backend terminal last lines; share only those |
| **503** `config_missing` / `campx_not_configured` / `not_configured` | Missing `APP_SECRET_KEY` / `CAMPX_CLIENT_HEADER_VALUE` / a `CAMPX_*_PATH` |
| **CORS error in browser console** | Page opened from an origin not in `FRONTEND_ORIGIN` |
| **Vite proxy error `ECONNREFUSED`** | Backend not running on 127.0.0.1:8000 |
| **"Missing environment variable"** | Variable not in `.env` (names must match `.env.example` exactly); restart backend after edits |

## 18. Every value that still needs your input

| Setting | Where from |
|---|---|
| `CAMPX_CLIENT_HEADER_VALUE` | DevTools, section 11A |
| `CAMPX_AUTH_MODE` (+ `CAMPX_TOKEN_HEADER`) | DevTools, section 11B step 5 |
| `CAMPX_TIMETABLE_PATH` | Confirm/adjust (query params?) via 11B |
| `CAMPX_ATTENDANCE_PATH`, `CAMPX_PROFILE_PATH`, `CAMPX_SUBJECTS_PATH` | 11C |
| `FRONTEND_ORIGIN`, `APP_ENV=production`, `ADMIN_TOKEN` | Only when deploying |
| `APP_SECRET_KEY` | Generated for you by `setup.ps1` |

## 19. Suggested order of work for ChatGPT

1. Confirm prerequisites (section 3) → run `scripts\setup.ps1` → show output tail.
2. `/health` check (section 9).
3. Run tests (section 14) → expect all passed.
4. Help the user obtain `X-Campx-Client` (11A) → restart → try login.
5. If login fails, map the error code using section 17 before touching code.
6. Walk through 11B for timetable; adjust `.env`; retry.
7. Walk through 11C for attendance/profile; extend normalizers **with a test** from the redacted shape.
8. Use sample imports as a fallback so the UI is useful meanwhile.
9. Only then consider deployment (README §7, SECURITY.md checklist).
