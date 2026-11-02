# Phase 5 — Security Audit

Date: 2026-11-01. Branch `test`. **No application code was modified.** Method: static review of routers, services, config, Docker/Compose and frontend; a route-by-route authorization map (AST script); git-history secret scan (patterns only, values never printed); dependency audit; and confirmation of the top findings with a throwaway script run against the **isolated `truhire_test` database** with synthetic data (the script refuses to run unless connected to a `*_test` database, and Qdrant/OpenSearch were pointed at a local stand-in server, so no real index or cloud service was touched). `.env` contents were not read or printed.

Status legend: **Confirmed** = reproduced locally; **Confirmed (config)** = visible in the committed configuration; **Hypothesis** = depends on deployment or needs more testing.

## 1. Summary
| ID | Severity | Finding | Status |
|---|---|---|---|
| SEC-01 | **Critical** | Any signed-in user can purge all resumes and requirements (`POST /api/retention/cleanup?retention_days=0`) | Confirmed |
| SEC-02 | **High** | Open self-registration: any visitor gets an account and full read/export of every candidate | Confirmed |
| SEC-03 | **High** | Registering an email on the admin list grants admin with no verification | Confirmed |
| SEC-04 | **High** | Other destructive and bulk-data routes need no admin role (reparse, reindex, bulk-delete, delete, export) | Confirmed |
| SEC-05 | **High** | Compose publishes Postgres, Redis (no password) and OpenSearch (security disabled) on all interfaces | Confirmed (config); reachability = Hypothesis |
| SEC-06 | **High** | Compose ships a fallback `SECRET_KEY` and database password that pass validation | Confirmed (config) |
| SEC-07 | Medium | No password policy (1-character password accepted); account enumeration on register | Confirmed |
| SEC-08 | Medium | Upload limits incomplete: no app-level size cap on JD/assistant uploads; no PDF page, zip-expansion or image-size limits | Confirmed (code) |
| SEC-09 | Medium | Cloud-fallback sends names, employers, schools to third-party LLMs (redaction covers email/phone/ID/address only) | Confirmed (code); policy decision |
| SEC-10 | Medium | nginx: no security headers, HTTP only | Confirmed (config) |
| SEC-11 | Medium | Containers run as root with default privileges | Confirmed (config) |
| SEC-12 | Medium | 24 h bearer tokens kept in `localStorage`; no revocation, logout or account deactivation | Confirmed (code) |
| SEC-13 | Low | Email recipient and subject written to logs | Confirmed (code) |
| SEC-14 | Low | Raw exception text returned to clients on two routes | Confirmed (code) |
| SEC-15 | Low | `APP_ENV` defaults to `development`, which skips the secret-length check | Confirmed (config) |
| SEC-16 | Info | Internal SSH target in `.env.example` (value withheld here) | Confirmed |
| SEC-17 | Low | No per-user daily cap on outbound email | Hypothesis |

Already fixed earlier on this branch and re-confirmed: **`GET /api/ai-audit` is admin-only** (recruiter gets 403, script check F).

## 2. Findings in detail

### SEC-01 Critical: retention cleanup open to every user
- **Where:** `backend/routers/retention.py:22-37` (`trigger_retention_cleanup` uses `get_current_user`, not an admin role) with an unbounded `retention_days` override.
- **Evidence:** as a freshly registered recruiter, `POST /api/retention/cleanup?retention_days=0` returned 200 and a synthetic candidate row went from 1 to 0. The cleanup also deletes files, Qdrant vectors, OpenSearch documents and requirements. A negative value moves the cutoff into the future.
- **Preconditions:** a valid token; with SEC-02 that is any visitor.
- **Impact:** irreversible loss of all candidate and requirement data by one request.
- **Remediation:** require `ROLE_ADMIN`; reject `retention_days` below the configured minimum (or drop the override from the API and keep it in settings); log who triggered it; consider a soft-delete window.
- **Regression test:** recruiter gets 403; admin with `retention_days=0` gets 422; admin default run succeeds.

### SEC-02 High: open registration plus a shared data pool
- **Where:** `backend/routers/auth.py` `register` (no invitation, approval or domain restriction); every authenticated route reads the same global candidate set.
- **Evidence:** `POST /api/auth/register` with a stranger's email and password `a` returned a working token with role `recruiter`; that token listed and exported all candidates (`GET /api/candidates`, `GET /api/export/candidates` both 200).
- **Impact:** anyone who can reach the app can download every resume (names, emails, phones, work history).
- **Remediation:** turn self-registration off by default; create users by admin invitation or restrict to approved email domains with email verification; keep the registration rate limit.
- **Regression test:** unauthenticated register returns 403 when disabled; admin-created user can log in.

### SEC-03 High: admin role granted by email string
- **Where:** `auth.py` `register`: `role = ROLE_ADMIN if email in settings.bootstrap_admin_emails`.
- **Evidence:** registering an email listed in `BOOTSTRAP_ADMIN_EMAILS` as a stranger returned `role = admin`.
- **Impact:** until the real admin registers (or at any time if that account is later deleted), whoever uses that address first, or anyone who can sign up with it, becomes admin, with access to roles, audit trail and (after SEC-01 is fixed) retention.
- **Remediation:** make bootstrap admin one-shot (only while no admin exists), require email verification, or create the first admin with a CLI command instead.
- **Regression test:** second registration with an admin-list email gets `recruiter`; with an existing admin the list is ignored.

### SEC-04 High: destructive and bulk routes need only "signed in"
- **Evidence (authorization map of 70 routes; only login/register are unauthenticated):** a recruiter got 202 on `POST /api/ingest/reparse`, 202 on `POST /api/ingest/reindex` and 200 on `POST /api/candidates/bulk-delete`. `DELETE /api/candidates/{id}`, `DELETE /api/job-descriptions/{id}` and `GET /api/export/candidates` are likewise available to every user.
- **Impact:** one low-privilege or self-registered account can delete or export everything, or trigger expensive reprocessing (resource exhaustion).
- **Remediation:** decide the permission model, then enforce it server-side: admins only for reparse, reindex, bulk-delete and full export; recruiters may delete only what they created (add ownership checks); add an audit entry for each.
- **Regression test:** matrix test, role by route, expecting 403 where the model says so.

### SEC-05 High: data stores published on every interface
- **Where:** `docker-compose.yml`: Postgres `${POSTGRES_PORT:-5432}:5432`, Redis `${REDIS_PORT:-6379}:6379` with `redis-server --appendonly yes` and **no password**, OpenSearch `9200` with `DISABLE_SECURITY_PLUGIN=true`, OpenSearch Dashboards `5601` with its security plugin disabled.
- **Impact (if the host is reachable from a network):** anyone can read the candidate index (full resume text) from OpenSearch with no credentials, read or flush Redis (cache, queued jobs, rate-limit counters), or try the default Postgres password. Redis write access would also let an attacker plant cache entries the app trusts.
- **Remediation:** remove `ports:` for postgres, redis, opensearch and dashboards (they only need the internal compose network), or bind them to `127.0.0.1`; set a Redis `requirepass`; enable the OpenSearch security plugin or keep it strictly internal; require `POSTGRES_PASSWORD` instead of defaulting it.
- **Regression test:** `docker compose config` check in CI that no data service has a non-loopback `ports:` entry.

### SEC-06 High: fallback secrets in Compose
- **Where:** `docker-compose.yml`: `SECRET_KEY: ${SECRET_KEY:-truhire_container_jwt_secret_key_change_me_outside_dev}` and `POSTGRES_PASSWORD:-truhire_secret`.
- **Impact:** if `.env` omits them the stack starts with publicly known values (the key is 52 characters, so the "at least 32" check passes). Anyone can then forge a token for any user id, including an admin.
- **Remediation:** use `${SECRET_KEY:?set SECRET_KEY in .env}` and the same for `POSTGRES_PASSWORD`, and refuse known placeholder values at startup.
- **Regression test:** startup fails when `SECRET_KEY` equals the placeholder.

### SEC-07 Medium: weak credentials handling
- **Evidence:** password `a` accepted; no length, breach or complexity check in `UserRegisterRequest`. `register` answers `400 "A user with this email already exists."` (account enumeration); `login` skips password hashing when the user does not exist (timing difference). Login is limited to 5/minute per client IP (counted correctly behind nginx after the rate-limit change on this branch). Passwords are hashed with bcrypt (good); inputs over 72 bytes are truncated by design.
- **Remediation:** minimum length 12 and a deny-list of common passwords; uniform responses and a dummy hash for unknown users; per-account lockout or backoff.

### SEC-08 Medium: upload and parsing limits
- **Where:** `ingestion.py:202-205` enforces `MAX_UPLOAD_MB` (15 MB), but `job_descriptions.py:795` and `assistant.py:323` read the whole upload with no cap; `parsing.py` has no PDF page limit, no maximum for decompressed zip/docx content (it opens the zip itself in the fallback), no image pixel limit before OCR, and no parse timeout.
- **Impact:** memory and CPU exhaustion by one crafted file. In Docker nginx caps request bodies at 50 MB, and the backend port is now bound to localhost, which reduces but does not remove this.
- **Remediation:** one shared size check for every upload route; cap pages, uncompressed bytes and pixels; run parsing with a timeout. Pillow and pypdf are on current patched versions.
- **Regression test:** oversize JD upload returns 413; a zip bomb sample is rejected.

### SEC-09 Medium: what the cloud fallback sends out
- **Where:** `router.py` redacts with `redact_pii(...)` (email, phone, national ID, street address, and a candidate name only when one is supplied). Resume parsing (`ai_service._parse_resume_window`) and email generation send resume text through the same router, so while the DGX is down the full text, including names, employers, schools and cities, can go to OpenRouter, Groq or Gemini.
- **Impact:** candidate personal data leaves your infrastructure to three third parties; this may conflict with privacy commitments or law (for example consent and cross-border transfer).
- **Remediation options (product decision):** (a) cloud fallback only for the chat assistant and never for resume or email features (fail instead); (b) add name and entity redaction before the call; (c) accept it and document it with provider data-processing terms. The audit trail already records each fallback call with `pii_redacted` in its details.

### SEC-10 Medium: web server hardening
- `frontend/nginx.conf` sets no `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` or HSTS, and listens only on port 80. **Assumption to verify:** TLS terminates in front (load balancer or reverse proxy). If not, bearer tokens and resumes cross the network in clear text.
- Remediation: add the headers, `server_tokens off`, and document or provide TLS termination.

### SEC-11 Medium: container privileges
- Both images run as root (no `USER`); no `read_only`, `cap_drop` or `no-new-privileges` in Compose; `restart: unless-stopped` and healthchecks are present (good).
- Remediation: add a non-root user to the backend image and `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]`; `nginx-unprivileged` for the frontend.

### SEC-12 Medium: session model
- Tokens are HS256 JWTs with `exp` (24 h default), verified with a pinned algorithm; they are stored in `localStorage`, so any future XSS would expose them (no XSS sink found: no `dangerouslySetInnerHTML`/`innerHTML`). There is no server-side revocation, logout invalidation or "disabled user" flag, so a leaver keeps access until expiry. Roles are re-read from the database on every request, so demotion takes effect immediately (good).
- Remediation: shorter access tokens with refresh, an `is_active` flag checked in `get_current_user`, and optionally an `HttpOnly` cookie.

### Low and informational
- **SEC-13:** `email_delivery.py:35,58` log the recipient address and subject at WARNING. Log the candidate id instead.
- **SEC-14:** `job_descriptions.py:806` returns `Error processing file...: {exc}` and `search.py:80` returns `str(exc)`; return a generic message and log the detail.
- **SEC-15:** `APP_ENV` defaults to `development`: the dev CORS regex is active and the secret-length check is skipped. Compose sets `production`; default the code to production.
- **SEC-16:** `.env.example` holds a real-looking `user@host` for `DGX_SSH_TARGET`; replace with a placeholder.
- **SEC-17:** `/api/email/send` accepts up to 50 recipients per call under the general rate limit; only shortlisted candidates with an address can be mailed and an idempotency key exists, so abuse is bounded, but there is no daily cap per user.

## 3. Controls reviewed and found sound
- **SQL injection:** ORM queries throughout; the only `text()` DDL uses table names from the model metadata.
- **Path traversal:** `resolve_stored_file` resolves and checks `is_relative_to(STORAGE_DIR)`; uploaded names are character-filtered and prefixed with a hash; tests cover traversal attempts.
- **SSRF:** all outbound HTTP goes to configured endpoints (DGX, Qdrant, OpenSearch, three fixed cloud API hosts); no user-supplied URL is fetched.
- **Open redirect:** the post-login `next` target passes through `safeAppPath`.
- **Email header injection:** messages are built with `EmailMessage`, which rejects newline-bearing headers.
- **CORS:** explicit origins with credentials; the permissive regex applies only when `APP_ENV` is development.
- **JWT:** algorithm pinned, `exp` verified, `sub` required; PyJWT replaces the unmaintained python-jose.
- **Secrets in source/history:** 68 commits scanned for API-key, private-key and token patterns: none found; committed example values are placeholders; `.env` files are untracked and ignored.
- **Dependencies:** Python audit clean and `npm audit` 0 vulnerabilities after this branch's upgrades.
- **Prompt injection and AI controls:** untrusted-content delimiters, resume injection screening, output guardrails and an AI audit trail with PII-redacted previews exist and are tested; the assistant now refuses off-topic requests.
- **Rate limiting:** per-user counting, Redis-shared, with in-memory fallback.

## 4. Tests performed
- Authorization map of 70 routes (script), history secret scan (68 revisions), dependency audits, static review of the files above.
- Local confirmation script against `truhire_test` (results A to F above). It created and then deleted only synthetic users and one synthetic candidate.

## 5. Limitations
- No container image vulnerability scan (no scanner available here), no dynamic scan or fuzzing, no TLS or network probing, no load testing.
- Real `.env`, DGX, Qdrant Cloud and SMTP were not contacted or inspected.
- Reachability of SEC-05 depends on the host firewall and network; SEC-02's impact depends on who can reach the app.
- The permission model for recruiters (what they may delete or export) is a product choice that remediation needs.

## 6. Prioritized remediation
1. **SEC-01** admin-only and bounded retention cleanup (small, urgent).
2. **SEC-06** and **SEC-05** Compose hardening: required secrets, no published data-store ports, Redis password.
3. **SEC-02** and **SEC-03**: disable open registration; one-shot admin bootstrap.
4. **SEC-04** role matrix with ownership checks and audit entries.
5. **SEC-07**, **SEC-08**, **SEC-12**: password policy, upload limits, session model.
6. **SEC-09**: decide the cloud-fallback data policy.
7. **SEC-10**, **SEC-11**, then the Low items.

## 7. Questions for you
1. Who can reach this app: internal network only, or the internet? (decides how urgent SEC-02/05 are)
2. Should users be able to register themselves, or should admins create accounts?
3. What may a recruiter do: delete or export any candidate, only their own, or neither?
4. Is TLS handled in front of nginx?
5. Which cloud-fallback policy for SEC-09: assistant only, redact names too, or accept?
