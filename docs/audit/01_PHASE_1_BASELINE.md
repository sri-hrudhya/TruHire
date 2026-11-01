# Phase 1 — Repository Baseline and Inventory

Date: 2026-11-01. Read-only phase. No application source, manifests, lockfiles, or runtime data were modified.

## 1. Commit and working-tree status
- Branch `main`, HEAD `7401d9a91fa1e93ac402b55abf9c5778f1ab1a79` ("Docs: Audit docs"). **Ahead of `origin/main` by 1 commit** (unpushed).
- Working tree (pre-existing, preserved untouched):
  - ` D docs/audit/TRUHIRE_AUDIT_PLAN.md` (deleted, unstaged)
  - Untracked: `docs/audit/00_…` to `10_…` plan files (and this report).
- No application files changed by this phase.

## 2. Inventory (method: `git ls-files`, classified by top-level path and extension)
Tracked files: **220**.

| Class | Count | Location |
|---|---|---|
| Frontend (src, tests, config) | 94 | `frontend/` (51 `.jsx`, 16 `.js`, 11 `.css`, 7 `.mjs`) |
| Backend | 67 | `backend/` (routers 15, services ~38, models/config/auth/worker) |
| Python tests | 19 | `tests/` (incl. `conftest.py`) |
| Scripts | 16 | `scripts/` (search_repo, setup_search, validate-* in .sh/.ps1 pairs) |
| Docs | 3 (+ audit plans untracked) | `docs/` (workflow `.mmd`/`.svg`) |
| Agent adapter docs | 3 | `adapters/` (CLAUDE, GEMINI, GPT_OSS) |
| Docker/deploy | `Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `.dockerignore` x2, `frontend/nginx.conf`, `run-docker.{sh,ps1,bat}`, `start-dgx-tunnel.sh`, `DOCKER.md` |
| Dependency/config | `pyproject.toml`, `uv.lock`, `requirements.txt` (339 lines), `frontend/package.json` + lock, `model_capabilities.yaml`, `.env.example`, `.impeccable` |
| Root docs | `README.md`, `PRODUCT.md`, `file-structure.md`, `frontend/DESIGN.md` |
| Migrations | **None found** (no alembic/migrations dir tracked) |
| CI | **None** (no `.github/`, no other CI config tracked) |

Top-level file-type counts: py 85, jsx 51, js 16, css 11, sh 10, md 10, ps1 9, mjs 7, zip 2.

### Tracked archives / samples (for review, contents not reproduced)
- `backend/backend.zip` (~1.0 MB, 150 entries) and `frontend/frontend.zip` (~1.25 MB, 113 entries) — tracked source snapshots committed inside the source tree. Possible stale duplicates; content/age/sensitivity not yet inspected.
- No tracked resumes/JDs found by filename. Resume/JD data lives in ignored dirs (below). Code files matching "resume/JD" are application code, not data.

## 3. Ignored / generated / local directories (not dumped)
| Path | Notes |
|---|---|
| `.venv/` | **Linux (WSL) uv venv, CPython 3.14** (`home=/home/Pavan/...`); not usable from Windows. Note `requires-python >=3.13` and Dockerfile uses 3.13. |
| `frontend/node_modules/`, `frontend/dist/` (3 files), `.vite/` | Node/Vite artifacts |
| `__pycache__/` dirs, `.pytest_cache/` | Python caches |
| `Camunda-resumes/` (45 files), `JD/` (1), `uploads/` (61), `logs/` (1) | **Runtime/candidate data, likely PII** — gitignored, not inspected |
| `.env`, `frontend/.env` | Secrets, present, not read beyond a redacted DB host/port check |
| `.agent/` (27), `.agents/` (17), `.gsd/` (28), `.claude/`, `.gemini/`, `.vscode/`, `.impeccable/hook.cache.json` | Agent/editor tooling |
| `PROJECT_RULES.md`, `VERSION`, `command.md` | Ignored local files in root |

## 4. Entry points and runtime surfaces
- **Backend app:** `backend/main.py` — `FastAPI(title=settings.APP_NAME, version="2.0.0")`.
  - Middleware: `SlowAPIMiddleware`, `ObservabilityMiddleware`, `CORSMiddleware` (regex origin only in dev env, `allow_credentials=True`, wildcard methods/headers).
  - Startup (`@app.on_event("startup")`, deprecated style): `init_opensearch_index()`, daemon thread `_warm_models` (local embeddings / reranker / Laya, conditional on settings), `asyncio.create_task(schedule_retention_cleanup_task())`. No shutdown hook found.
  - Routers (15, registered in a loop): auth, ingestion, job_descriptions, candidates, search, analytics, export, retention, email, ai_audit, demands, meta, reviews, users, assistant. `backend/routers/` contains exactly these 15 modules (plus `__init__`).
  - Health: `GET /api/health`.
- **Worker:** `backend/worker.py` — optional arq worker (`arq backend.worker.WorkerSettings`), used only when `USE_ARQ_QUEUE=true`; default ingestion path uses FastAPI `BackgroundTasks`.
- **Other backend scripts:** `backend/scripts/eval_retrieval.py`, `scan_resume_injections.py`.
- **LLM providers:** `services/llm/providers/{gemini,groq,openrouter}.py`, `vllm.py`, `router.py`, `laya_service.py`, `local_embeddings.py`.
- **Frontend:** React 18 + Vite 6 + react-router-dom 6, `frontend/src/main.jsx`/`App.jsx`. Pages: Analytics, Auth, CandidateDetail, Email, IngestionHistory, Ingestion, JobDescriptions, Search. Contexts: Auth, Meta, Theme. Dev proxy `/api` → backend; dev **throws** if `VITE_BACKEND_URL`/`PORT` unset. Production served via nginx (`frontend/nginx.conf`).
- **Compose services:** postgres 16, redis 7, opensearch 2.12, opensearch-dashboards, backend, frontend. Volumes: postgres_data, redis_data, opensearch_data, uploads_data, logs_data, model_cache. **Qdrant is not a compose service** (known context listed Qdrant; to be reconciled in Phase 2/7). No separate arq worker service seen in compose (to verify).

## 5. Validation commands and results
| Check | Source | Result |
|---|---|---|
| Frontend unit tests: `npm test` (6 node test files) | `frontend/package.json` | **PASS** (all PASS lines; no failures seen) |
| Frontend build: `vite build` (output redirected to scratchpad, repo `dist/` untouched) | package.json | **PASS** — 1716 modules, JS 417.9 kB (125.5 kB gzip), CSS 44 kB |
| Python syntax: `py_compile backend/main.py` (system Python 3.13) | — | OK |
| Python tests: `pytest` (`testpaths=tests`, 19 files) | `pyproject.toml` | **NOT RUN** (see limitations) |
| Compose validation: `docker compose config -q` | docker-compose.yml | **NOT RUN** — `docker` not installed in this shell |
| Browser E2E: `frontend/tests/e2e/search-modes.spec.mjs` (playwright-core) | — | NOT RUN (needs running stack) |
| Lint / type-check | — | **None configured** (no ruff/mypy/eslint config; `scripts/validate-*.sh` are agent-config validators, not code lint — not run) |

## 6. Existing failures and limitations
1. **pytest not run.** Reasons: (a) `.venv` is a Linux venv, unusable from Windows; (b) system Python 3.13 lacks pytest/fastapi/sqlalchemy/psycopg; (c) `tests/conftest.py` connects to the Postgres server on `127.0.0.1:5432` (port is open) and **creates a `truhire_test` database on demand** — a write to the live DB server, so I did not run it without your approval.
2. Docker unavailable here, so compose config and image builds are unvalidated.
3. No CI, no lint, no type-check, no migrations tooling → baseline health relies on pytest + node tests only.
4. Side effect to disclose: `py_compile` may have written bytecode under the already-ignored `backend/__pycache__/`. No tracked file affected (`git status` shows only pre-existing changes).

## 7. Ambiguities for later phases
- Purpose, age, and sensitivity of `backend/backend.zip` and `frontend/frontend.zip` (tracked, ~2 MB).
- Qdrant: referenced in README-level context and startup log text (`qdrant_quantization`), but absent from compose — where does it run?
- How DB schema is created/evolved with no migrations (likely `create_all` in `database.py`; verify in Phase 2).
- `requirements.txt` (339 lines) vs `pyproject.toml`/`uv.lock` — which is authoritative; `requirements.txt` vs Dockerfile (uses `uv sync`).
- Python version drift: `.venv` 3.14 vs Docker 3.13 vs `>=3.13`.
- `.env` and `frontend/.env` are present but ignored (confirmed not tracked); Phase 5 should check `.env.example` and git history for secret leakage.
- Whether an arq worker runs in compose when `USE_ARQ_QUEUE=true`.
- `adapters/`, `scripts/validate-*`, `.agent*`, `.gsd` look like AI-agent tooling rather than product code — classify as non-runtime in Phase 4.
- Deleted `TRUHIRE_AUDIT_PLAN.md` — intentional replacement by the numbered plans? (left as is).

## 8. Confirmation
No application source, manifests, lockfiles, or runtime data were modified. The only file created is this report.
