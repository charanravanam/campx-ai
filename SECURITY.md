# Security model

## What is protected and how

| Asset | Protection |
|---|---|
| Student password | Sent to CampX once over HTTPS; never stored, never logged, never in URLs. Failed validation responses do not echo it. |
| CampX token + cookies | Stored only server-side, **Fernet-encrypted** (key derived from `APP_SECRET_KEY`) in SQLite. Never returned by any endpoint. |
| Website session | Random 256-bit id in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` + `__Host-` prefix in production). Only its SHA-256 hash is stored. Expires after `SESSION_TTL_HOURS` and never outlives the CampX token expiry. Logout deletes the row (replaying an old cookie fails). New login replaces any presented session (no fixation). Max `MAX_SESSIONS_PER_USER` sessions per student. |
| Student identity in DB | HMAC of tenant+login ID — no email stored. A masked hint (`al***@…`) is kept for display. |
| Per-student isolation | Every query is keyed by the session's user key; each upstream call uses only that student's stored session. Imported JSON is keyed the same way. Covered by tests. |
| CSRF | Every `POST/PUT/PATCH/DELETE` (including login) needs `X-CSRF-Token` equal to a signed CSRF cookie **and** an allowed `Origin` (or `Referer`). |
| CORS | Only origins in `FRONTEND_ORIGIN`, with credentials. |
| Brute force | Per-account and per-IP sliding-window limits on failed logins (`429` + `Retry-After`). CampX is not contacted while blocked. |
| Input | Pydantic validation, length limits, control characters rejected, import size limit (streamed), parameterised SQL only, unknown JSON structures rejected with `422`. |
| Upstream | Fixed base URL, paths only from server config, redirects not followed, timeouts, response size cap, upstream bodies never forwarded. |
| Admin | `/api/admin/*` needs a separate `X-Admin-Token`; disabled (404) unless `ADMIN_TOKEN` is set; a student session is not admin. |
| Headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` and a restrictive CSP on API responses, HSTS in production. |
| Logging | Request bodies, cookies and tokens are never logged. A redaction filter is a second safety net. |

## What this does NOT do

* No MFA/CAPTCHA bypass. MFA accounts are refused with a clear message.
* No silent re-authentication (would require storing passwords).
* Rate limiting is in-memory: restart clears it; multiple workers don't share it. Use Redis or a gateway limiter for multi-instance deployments.
* SQLite is fine for a single server. For several servers move sessions to PostgreSQL/Redis (same `SessionStore` interface).
* If someone obtains both the database file **and** `APP_SECRET_KEY`, upstream sessions can be decrypted. Keep them in different places.
* Local development uses plain HTTP: cookies lack `Secure` and traffic is unencrypted on localhost only. Never expose the dev setup to the internet.
* The `X-Campx-Client` value is not a personal secret but is still kept in server config only.
* Whether a third-party app may use CampX's login at all is governed by CampX/GNITC terms. Check them. If not permitted, use `DATA_SOURCE=imported`.

## Production checklist

- [ ] `APP_ENV=production`; site served over HTTPS only; HSTS reaching the browser.
- [ ] `FRONTEND_ORIGIN` lists only your real `https://` origin(s).
- [ ] `APP_SECRET_KEY` is random, 32+ chars, stored in your host's secret manager — not in Git, chat or screenshots.
- [ ] `.env` and `backend/data/` are not in Git, not world-readable, and are backed up securely.
- [ ] uvicorn bound to `127.0.0.1` behind a TLS reverse proxy; `--proxy-headers --forwarded-allow-ips` set to the proxy only.
- [ ] `/docs` and `/openapi.json` are off (automatic in production).
- [ ] `ADMIN_TOKEN` empty (disabled) or 32+ random chars, only reachable from a trusted network.
- [ ] Firewall: only 80/443 public; port 8000 not exposed.
- [ ] Log files reviewed: no passwords/tokens (they shouldn't be there).
- [ ] Dependencies pinned and updated periodically (`pip list --outdated`, `npm audit`).
- [ ] Tests green on the deployed commit.

## If something leaked — rotate and clean up

1. **A student password was exposed (chat, screenshot, log):** that student changes their CampX password immediately.
2. **Cookies / tokens exposed:** log out of CampX everywhere (CampX security settings), change the password. Then end sessions here: student clicks *Log out*, or you run
   `curl -X POST https://your.site/api/admin/revoke-all -H "X-Admin-Token: <ADMIN_TOKEN>"`.
3. **`APP_SECRET_KEY` exposed:** generate a new one (`python scripts/generate_secret.py`), replace it in `.env`, restart. Existing sessions become undecryptable and are discarded automatically; everyone signs in again. Imported JSON stays but is re-keyed to a different user key — students re-import.
4. **`ADMIN_TOKEN` exposed:** change it and restart.
5. **Secret committed to Git:** rotating is mandatory (history keeps it). Remove it from history with `git filter-repo`, force-push, and treat the old value as burned.
6. **Database file leaked:** passwords are not in it; upstream blobs are encrypted. Rotate `APP_SECRET_KEY` anyway and revoke all sessions.
7. Delete `backend/data/campx_ai.db` (and `-wal`/`-shm`) to wipe everything while the app is stopped.
