# CampX AI

A student dashboard for GNITC. A student signs in with their **own** CampX account and sees their own profile, timetable, attendance and subjects.

* **Backend:** FastAPI (Python 3.11+), SQLite sessions, HTTPX.
* **Frontend:** React 18 + Vite.
* **Status:** the website, security layer, import flow and all calculations are built and tested against a *mocked* CampX. **Nothing here has been tested against the real CampX service.** See [BUILD_REPORT.md](BUILD_REPORT.md) for exactly what was and was not verified.

> New to this? Read **[steps_for_chatgpt.md](steps_for_chatgpt.md)** — a step-by-step guide written so ChatGPT (or any helper) can walk you from zero to a running app.

---

## 1. Quick start (Windows PowerShell)

Prerequisites: **Python 3.11+** (tick "Add to PATH"), **Node.js 20+ LTS**.

```powershell
cd path\to\campx-ai
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1    # one time
notepad .env                                                    # fill in CAMPX_CLIENT_HEADER_VALUE (section 3)
powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1  # opens backend + frontend windows
```

Open **http://localhost:5173** (use `localhost`, matching `FRONTEND_ORIGIN`).
Health check: http://127.0.0.1:8000/health — API docs: http://127.0.0.1:8000/docs (development only).

Manual equivalent (two terminals):

```powershell
# Terminal 1 - backend
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 - frontend
cd frontend
npm run dev
```

macOS/Linux: same commands with `python3 -m venv backend/.venv`, `backend/.venv/bin/python`, and `cp .env.example .env` (then put the output of `python scripts/generate_secret.py` after `APP_SECRET_KEY=`).

## 2. How it works

```
Browser (React)  --/api-->  Vite proxy (dev)  -->  FastAPI backend  --HTTPS-->  api.campx.in
   only holds an HttpOnly                           holds each student's own
   random website-session cookie                    CampX session, encrypted in SQLite
```

* The student's password is sent to CampX once, at login, and is **never stored or logged**.
* Each login creates a separate website session and a separate stored CampX session. There is no shared/global CampX session.
* The browser never sees CampX tokens or cookies.

## 3. Configuration you must supply

Edit `.env` (created by `setup.ps1`; never commit it). Full list with comments: [.env.example](.env.example).

| Setting | Required? | What to do |
|---|---|---|
| `APP_SECRET_KEY` | **Yes** | `setup.ps1` generates it. Or: `python scripts/generate_secret.py` |
| `CAMPX_CLIENT_HEADER_VALUE` | **Yes, for live login** | See "Finding X-Campx-Client" below. Login answers `503` until set. |
| `CAMPX_AUTH_MODE` | Verify | `cookie` (default), `bearer` or `header`. **Unverified** — confirm with DevTools. |
| `CAMPX_TIMETABLE_PATH` | Verify | Prefilled with the route you observed: `/student-api/classroom-timetables`. **Not verified to work.** |
| `CAMPX_PROFILE_PATH`, `CAMPX_ATTENDANCE_PATH`, `CAMPX_SUBJECTS_PATH` | Optional | Empty until you discover the real route. Until then use JSON import. |
| `DATA_SOURCE` | Optional | `auto` (default), `campx`, or `imported`. |

### Finding X-Campx-Client

The official CampX web app sends an `X-Campx-Client` header on its own login request. To read it **from your own browser**:

1. Open https://gnitc.campx.in in Chrome, press **F12** → **Network** tab, tick **Preserve log**.
2. Sign in normally. Click the request named `login` (`/auth-server/auth-v2/login`).
3. **Headers → Request Headers → `X-Campx-Client`**. Copy **only that one value** into `.env`.
4. Do **not** copy or share the `Cookie` header, the response body, or your password.

Only use a value that the public web app itself sends to every visitor. If it appears to be a personal or confidential key, or if CampX's terms don't allow third-party apps to use it, stop and use the JSON-import route instead. Never invent a value.

## 4. Data sources

| `DATA_SOURCE` | Behaviour |
|---|---|
| `campx` | Live CampX only. A kind with no configured path returns `503 not_configured`. |
| `imported` | Only JSON you imported (Settings → Import). CampX is never called for data. |
| `auto` *(default)* | Try live. If the path is unset, returns 404, or the shape is unrecognised, fall back to your imported JSON. Session errors (`401`), `403`, `429`, `5xx`, timeouts are **not** hidden by fallback. If nothing exists you get an empty state with an explanation. |

Every API response and every page shows its **source** (`campx`, `imported`, `derived`, `none`) so imported data is never mistaken for live data.

Synthetic examples for testing: `backend/sample_data/*.json` (all **fake**). Import them from **Settings**.

## 5. Tests and builds

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-tests.ps1
# or manually:
cd backend ; .venv\Scripts\python.exe -m pytest -q
cd ..\frontend ; npm run build
```

Tests mock every CampX call; they never touch the network or need real credentials.

## 6. Documentation index

* [steps_for_chatgpt.md](steps_for_chatgpt.md) — full beginner handoff guide
* [SECURITY.md](SECURITY.md) — security model, limits, production checklist, credential rotation
* [docs/API.md](docs/API.md) — endpoints and response shapes
* [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — errors and fixes
* [BUILD_REPORT.md](BUILD_REPORT.md) — what was built and verified

## 7. Production deployment (summary)

1. Serve the site over **HTTPS only**. Set `APP_ENV=production`, `FRONTEND_ORIGIN=https://your.site`. The backend refuses to start in production with a weak secret or non-HTTPS origin.
2. Build the frontend: `cd frontend; npm run build`; serve `frontend/dist` from the same site as the API (reverse proxy `/api` and `/health` to uvicorn) so cookies stay first-party.
3. Run uvicorn without `--reload`, bound to `127.0.0.1`, behind a reverse proxy (Caddy/nginx) that terminates TLS. Add `--proxy-headers --forwarded-allow-ips=<proxy ip>` so rate limiting sees real client IPs.
4. Back up/restrict `backend/data/`. Use the checklist in [SECURITY.md](SECURITY.md).

## 8. Known limitations

* Not tested against real CampX. Login body/headers follow what you observed; follow-up authentication and data routes are configuration.
* **MFA is not supported.** If CampX says MFA is required you get a clear message and no session is created.
* When the CampX session expires, the student must sign in again (the password is deliberately not stored, so silent re-login is impossible).
* Login rate limiting is in-memory (single process).
* Profile photos hosted behind CampX auth may not load in the browser; initials are shown instead.

## Attendance forecasting
Import attendance JSON in Settings, then open Attendance. Threshold maths uses exact class counts (never the rounded percentage). Recovery dates use real upcoming sessions from the dated timetable and are shown only when enough sessions exist. Present/Absent marks are a separate, resettable ledger labelled "Student Simulation"; the imported baseline is never modified. Details, limits and unverified items: see `BUILD_REPORT.md`.

API: `GET /api/attendance/forecast?target=75&lab_units=session|period`, `POST|DELETE /api/attendance/adjustments`, `POST /api/attendance/scenario` (nothing saved).
