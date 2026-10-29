# API reference

Interactive docs (development only): **http://127.0.0.1:8000/docs**

All errors look like `{"error": {"code": "...", "message": "..."}}`.
State-changing requests (`POST`/`DELETE`) need the header `X-CSRF-Token` (from `GET /api/auth/csrf`) **and** an allowed `Origin`.
All `/api/*` student endpoints need the session cookie set by login (`401 not_authenticated` otherwise).

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Status, DB check, which config is present (no secrets) |
| `GET /api/auth/csrf` | none | `{csrf_token}`; also sets the CSRF cookie |
| `POST /api/auth/login` | CSRF | Body `{"loginId","password"}` → `{authenticated, user, expires_at, csrf_token}` + session cookie |
| `GET /api/auth/me` | session | User hint, expiry, `data_source`, `live_endpoints`, `imports` |
| `POST /api/auth/logout` | CSRF | Deletes the server session, clears cookies |
| `GET /api/campx/profile` | session | **Live only**, normalised profile |
| `GET /api/campx/timetable` | session | **Live only**, normalised entries |
| `GET /api/profile` | session | Source-aware profile `{source, notice, profile}` |
| `GET /api/timetable` | session | `{source, notice, entries[]}` |
| `GET /api/timetable/today` | session | `{day, time, entries, class_count, current_class, next_class, upcoming}` (timezone `APP_TIMEZONE`) |
| `GET /api/attendance?target=75` | session | `{source, notice, target, overall, subjects[]}`; `target` integer 1–100 |
| `GET /api/subjects` | session | `{source, notice, derived, subjects[]}` |
| `POST /api/import/timetable` · `attendance` · `profile` · `subjects` | session + CSRF | Raw JSON body (≤ `MAX_IMPORT_BYTES`); stored for **your account only** |
| `GET /api/import/status` | session | Which kinds you imported and when |
| `DELETE /api/import/{kind}` | session + CSRF | Remove one import |
| `GET /api/admin/stats`, `POST /api/admin/purge-expired`, `POST /api/admin/revoke-all` | `X-Admin-Token` | Disabled (404) unless `ADMIN_TOKEN` set |

## Error codes

| HTTP | code | Meaning |
|---|---|---|
| 401 | `not_authenticated` | No/invalid/expired website session |
| 401 | `invalid_credentials` | CampX rejected the login ID/password |
| 401 | `campx_session_expired` | CampX session expired; our session was deleted — sign in again |
| 403 | `csrf_failed` / `origin_not_allowed` | CSRF or origin check failed |
| 403 | `mfa_unsupported` | CampX requires MFA; no session created |
| 403 | `upstream_forbidden` | CampX itself answered 403 |
| 404 | `upstream_not_found` | Configured CampX path doesn't exist |
| 413 | `payload_too_large` | Body over limit |
| 422 | `validation_error` / `unsupported_structure` / `too_many_entries` | Bad input / unknown JSON shape |
| 429 | `too_many_attempts` / `upstream_rate_limited` | Our login limiter / CampX's limiter (see `Retry-After`) |
| 502 | `upstream_unavailable` / `upstream_unreachable` / `upstream_malformed` / `campx_auth_not_established` | CampX down, unreachable, bad JSON, or nothing usable for `CAMPX_AUTH_MODE` |
| 503 | `config_missing` / `campx_not_configured` / `not_configured` | Missing `APP_SECRET_KEY` / `CAMPX_CLIENT_HEADER_VALUE` / a live path |
| 504 | `upstream_timeout` | CampX didn't answer in time |

## Normalised shapes

* **Timetable entry:** `{day, start "HH:MM", end, subject_code, subject_name, faculty, room, kind: "class"|"break"|"free"}`
* **Profile:** `{full_name, roll_number, email, photo_url, branch, course, batch, semester, classroom, section}` (any may be `null`)
* **Attendance subject:** `{subject_code, subject_name, attended, total, percentage, percentage_basis: "counts"|"reported"|null, status: "ok"|"low"|"unknown", classes_needed, classes_can_miss}`
* **Subject:** `{subject_code, subject_name, faculty, credits, category, semester}`

## Accepted import structures (known, deliberately limited)

* **Timetable:** flat list of periods; `{"entries"|"timetable"|"data"|…: [...]}`; weekday-keyed `{"Monday": [...], "Tue": [...]}`; day blocks `[{"day":"Monday","periods":[...]}]`. Period fields (aliases): `day|dayOfWeek`, `startTime|start|from`, `endTime|end|to`, `subjectName|subject|subject.name`, `subjectCode|subject.code`, `faculty|teacher`, `room|classroom`. Times: `9:00`, `09:00:00`, `9:00 AM`, ISO datetimes. Day numbers: 1=Monday…7=Sunday. `type: "Break"/"Lunch"` → `break`; no subject → `free`.
* **Attendance:** list or `{"subjects"|"attendance"|"data": [...]}`; each with subject name/code and either `attended`+`total` (aliases `present`, `conducted`, `held`; or `total`+`absent`) or a `percentage`.
* Anything else → `422 unsupported_structure`. The field aliases are **assumptions** about CampX naming and are unverified against real CampX responses.

## Attendance maths

Target `T` (integer %), attended `a`, total `t`:

* Classes to attend in a row: smallest `n ≥ 0` with `(a+n)/(t+n) ≥ T/100` → `n = ceil((T·t − 100·a)/(100 − T))` (0 if already met; impossible when `T = 100` and any class was missed).
* Classes you can miss: largest `s ≥ 0` with `a/(t+s) ≥ T/100` → `s = floor((100·a − T·t)/T)`.

Verified by brute force over many `(a, t, T)` combinations in `tests/test_calculations.py`. Your institution's real minimum/condonation rules may differ; the target is user-selectable and disclosed in the UI.
