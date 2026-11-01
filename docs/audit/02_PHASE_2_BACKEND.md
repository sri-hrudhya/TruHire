# Phase 2 — Backend Dependency and Reachability Audit

Date: 2026-11-01. Branch `test`. Read-only: no application source edited. Scratch scripts lived outside the repo.

## 1. Architecture and entry points (confirmed)
- **API:** `backend/main.py` → `FastAPI` app; 15 routers registered in a loop (auth, ingestion, job_descriptions, candidates, search, analytics, export, retention, email, ai_audit, demands, meta, reviews, users, assistant) + `GET /api/health`.
- **Middleware:** SlowAPI (rate limiting), `ObservabilityMiddleware`, CORS.
- **Startup (`on_event`, deprecated; no shutdown hook):** `init_opensearch_index()`; daemon thread warming local embeddings / reranker / Laya (each env-gated); `asyncio.create_task(schedule_retention_cleanup_task())`.
- **Schema management:** no Alembic. `backend/database.py` runs `Base.metadata.create_all` plus hand-written `ALTER TABLE … ADD COLUMN IF NOT EXISTS` and a generic "add missing model columns" routine (line ~101). Additive only; no drop/rename/type-change path (hypothesis: schema drift risk, revisit in Phase 7).
- **Worker:** `backend/worker.py` (arq) wraps `routers.ingestion.process_batch`; only used when `USE_ARQ_QUEUE=true`. The enqueue side is `routers/ingestion.py:214`. **No worker service exists in `docker-compose.yml`** → enabling the flag in compose would enqueue jobs nobody consumes (confirmed by grep; needs product decision).
- **CLI/ops scripts (documented in README):** `backend/scripts/eval_retrieval.py`, `backend/scripts/scan_resume_injections.py` (`--delete` is destructive).
- **External services:** Postgres (SQLAlchemy/psycopg), Redis (cache + arq), OpenSearch (compose, local), **Qdrant Cloud** (via `.env`, required by compose), vLLM/DGX OpenAI-compatible endpoint (`services/llm/vllm.py`), local fastembed embeddings, optional reranker, Laya.

## 2. Graph method and limitations
- Python `ast` walk over `backend/**/*.py` and `tests/*.py` (86 modules); resolved `import`/`from … import` incl. relative imports and `from pkg import submodule`; reachability = DFS from `backend.main` + `backend.worker`, treating parent packages as implicitly imported.
- Also scanned for `__import__`/`importlib`/string refs to `backend.*`, and counted whole-word references of every undecorated top-level def/class across backend+tests.
- **Limits:** `getattr`-based dispatch, FastAPI `Depends` wiring, SQLAlchemy model discovery, entry points defined in docs/compose, and the two conflict-broken test files (SyntaxError, so their imports are invisible to the graph) are not fully captured. Frontend callers of API routes are Phase 3.

## 3. Reachability result
57 backend modules reachable from `main`/`worker`. Not reached from runtime entry points:

| Module | Imported by | Classification | Evidence | Confidence |
|---|---|---|---|---|
| `backend/evaluation/metrics.py` (+pkg) | `scripts/eval_retrieval.py`, `tests/test_retrieval_evaluation.py` | **Operational / test-supported** | CLI usage in docstring; tested | High (keep) |
| `backend/scripts/eval_retrieval.py` | none (CLI) | **Operational** | README/docstring `python -m` usage | High (keep) |
| `backend/scripts/scan_resume_injections.py` | `tests/test_ai_governance.py` | **Operational + tested** | README line ~178 | High (keep) |
| `backend/services/llm/providers/gemini.py` (110 lines) | nothing | **Potentially orphaned** | see below | **High** that it's off the runtime path; removal is a product decision |
| `providers/groq.py` (103) | nothing | same | same | High |
| `providers/openrouter.py` (105) | nothing | same | same | High |

**Provider modules evidence:** `services/llm/router.py` (29 lines) docstring says "DGX/vLLM-only… Cloud provider modules are intentionally not part of the runtime path" and `chat_completion` delegates only to `vllm`. No `import`, string reference, `importlib`, test, compose or script mentions `providers.*` (only their own files). Related config left behind: `OPENROUTER_API_KEY_1/2`, `OPENROUTER_CHAT_MODEL`, `GROQ_API_KEY_1/2`, `GROQ_MODEL`, `GEMINI_API_KEY_1-3`, `GEMINI_CHAT_MODEL` in `config.py` (lines ~53-66) used only by those modules. History: files predate the "DGX-only" change (`59c443d Update: Clean all the codebase`). Recommendation: **retain pending decision**; if cloud fallback is permanently dropped, remove modules + settings together (also relevant to Phase 5: dormant API-key settings and data-egress surface).

### Unreferenced top-level definitions (name appears exactly once in backend+tests)
| Symbol | Location | Note | Confidence |
|---|---|---|---|
| `cache_user_session`, `get_cached_user_session` | `services/common/cache.py:161,167` | session-cache helpers never called | Medium (check auth flow intent) |
| `ask_choice`, `ask_score_batch` | `services/llm/laya_service.py:184,194` | Laya helpers not called; may be public API for planned use | Medium-Low |
| `upsert_candidate` | `services/retrieval/qdrant.py:165` | single-item upsert; ingestion likely uses batch variant | Medium |

None are removal-approved; all need Phase 4 corroboration (decorators excluded from this scan, so routes are not in this list).

## 4. Router → service map (route count; non-trivial service imports)
- auth 3, users 2, demands 6, reviews 7, meta 1, ai_audit 1: DB-only (models/auth).
- search 3 → `retrieval.search`, `retrieval.filters`.
- candidates 8 → cache, storage, opensearch, qdrant.
- job_descriptions 15 → classification, requirement_history, parsing, storage, `llm.ai_service`, filters, search, cache.
- ingestion 7 → chunking, injection_screen, pii, parsing, storage, ai_audit, ai_service, opensearch, qdrant, filters, cache.
- email 7 → email_delivery, ai_service, cache. export 1 → common.export. retention 2 → common.retention. analytics 1 → cache.
- assistant 5 → classification, parsing, storage, ai_service, `llm.router`, search (also uses `__import__("datetime")` ×3 at lines ~198/250/262 — harmless but unidiomatic; not a module-loading risk).
- Total ≈ 68 route handlers. Auth coverage per route is a Phase 5 task.

## 5. Dynamic / runtime references requiring validation
- Env-gated: `EMBEDDING_PROVIDER`, `RERANKER_ENABLED` (default False), `LAYA_ENABLED` (default **True**), `SEARCH_LLM_RERANK_ENABLED` (False), `USE_ARQ_QUEUE` (False). Gated code is reachable by import so was classified reachable.
- `pip` optional extra `laya` (`pyproject [project.optional-dependencies]`) vs `LAYA_ENABLED=True` default and `laya_service` import in `main` — confirm behaviour when the package is absent (warm-up swallows exceptions; runtime path unverified).
- Tests patch strings like `backend.services.llm.ai_service.llm_extract_jd_filters` (monkeypatch); these couple tests to function names.
- `main.py` startup uses `threading` + `asyncio.create_task` without handle retention or shutdown cancel.

## 6. Test ↔ module map (summary)
- Heaviest coverage: `main` + routers via TestClient in `test_ai_governance`, `test_requirement_match_threshold`, `test_ingestion_history_and_progress`, demands/JD tests; retrieval pieces in `test_search_cache_perf`, `test_fit_scoring`, `test_retrieval_evaluation`.
- **No test imports** (statically): `routers.candidates`, `routers.email`(only via app), `routers.export`, `routers.analytics` (one), `services.common.email_delivery/export/retention/requirement_history/observability`, `services.ingestion.storage/pii`, `services.llm.local_embeddings`, `llm.laya_service` (only governance test). Route-level tests via `main` may still cover some; no coverage tool is configured, so coverage is **unmeasured**.
- Two test files (`test_location_role_filters`, `test_requirement_status_and_email_history`) have committed merge-conflict markers; five more depend on the first. Their module coverage is invisible until fixed (Phase 1 Finding A).

## 7. Targeted checks performed
- AST import graph + reachability (above); SyntaxError detection (2 test files).
- Grep for provider references across code/tests/compose/docs; read `router.py` in full.
- Compose/Dockerfile grep for worker, arq, qdrant: no worker service; Qdrant is cloud-only (required env vars).
- Inspected `JDStatusRequest`, `PositionResponse`, `no_of_positions` schema to explain Phase 1 test failures:
  - `no_of_positions` is `Optional[int]`, `ge=0` (default None, 0 allowed); failing tests expect default 1 and rejection of 0 → **hypothesis: tests lag a deliberate schema change** (models.py comment: "NULL on demands made before this field"). Needs product confirmation.
  - Status test: `PUT …/status` with only `{"status":"Fulfilled"}` returns 422; `JDStatusRequest` also accepts `candidate_ids` and the frontend test says "a status that needs extra data sends it" → **hypothesis: Fulfilled now requires `candidate_ids`; test stale**. Not yet verified in `set_jd_status`.

## 8. Unresolved questions
1. Are cloud LLM providers (Gemini/Groq/OpenRouter) permanently retired? (Decides removal of 3 modules + 8 settings.)
2. Should the arq worker exist in compose, or should `USE_ARQ_QUEUE` be removed/documented as unsupported there?
3. Intended default for `no_of_positions` and whether 0 is valid (the failing tests encode the old rule).
4. Does `LAYA_ENABLED=True` work without the optional `laya` package installed?
5. Are `cache_user_session`/`get_cached_user_session` planned for the auth path?
6. What replaces migrations for destructive schema changes?
7. Real route/service coverage — no coverage tooling exists.

## 9. Confirmation
No application source, manifests, lockfiles, or runtime data modified. Files created/edited: this report and the Phase 1 addendum. `.venv-win` is a local ignored environment.

---

## Addendum — owner clarifications and re-test (2026-11-01)

### A. Cloud LLM providers: intended fallback chain, currently NOT wired on this branch (confirmed)
Owner statement: Gemini/Groq/OpenRouter are the chat-assistant fallback when the DGX Qwen (port 8000) is unavailable; each has 3 keys that should rotate; the assistant must not add latency, and must work well with the DGX Qwen too.
- The `dev` branch `backend/services/llm/router.py` implemented this chain (vLLM, then OpenRouter, then Groq, then Gemini, falling back only on connection/timeout/5xx).
- Commit `59c443d "Update: Clean all the codebase"` (on `main`/`test`; `dev` is 15 commits behind) replaced it with a vLLM-only router. So the provider modules are **not orphaned by intent; they were disconnected by a regression**. Classification changes from "potentially orphaned" to **"intended optional-provider, currently unwired: restore, do not delete"**.
- Gaps to fix when restoring (Phase 9, needs approval):
  1. **Key-count mismatch:** `config.py` has `OPENROUTER_API_KEY_1/2`, `GROQ_API_KEY_1/2`, `GEMINI_API_KEY_1-3`; the owner has 3 keys per provider. Add `_3` for OpenRouter and Groq, and make the modules iterate whatever keys exist.
  2. **Latency:** `VLLM_TIMEOUT=120s` means a dead DGX can block a chat request for up to 2 minutes before fallback. Recommended: a separate short connect timeout (about 2-3 s) plus a moderate read timeout on the chat path, and a **circuit breaker** (after N consecutive vLLM transient failures, skip vLLM for 30-60 s and probe in the background) so later requests go straight to a cloud provider.
  3. **Error matching by substring** of `RuntimeError` text is brittle; use typed exceptions (`httpx.ConnectError`/`TimeoutException`, status >= 500, 429).
  4. **Key rotation:** round-robin start index per provider (not always key 1), per-key cooldown on 429/timeout, then move to the next provider when keys are exhausted.
  5. Cloud calls send candidate/JD text off-premises. Needs a data-egress decision (Phase 5/6): redact PII before cloud calls, or limit cloud fallback to non-PII chat turns.
  6. Confirm `enable_thinking` (Qwen-only) handling and token limits on cloud models; embeddings stay local (unchanged).
- Not implemented: the audit stays read-only until you approve the change set.

### B. Unreferenced helpers: owner direction
- `cache_user_session` / `get_cached_user_session` (`cache.py:161,167`): owner confirms Redis already covers sessions. **Removal candidate, confidence High** (no callers).
- `ask_choice` / `ask_score_batch` (`laya_service.py:184,194`): owner says scoring already uses reranker + embeddings. **Removal candidate, confidence Medium-High**; confirm in Phase 6 that no planned path needs them.
- `upsert_candidate` (`qdrant.py:165`): still unreferenced; **Medium**, no owner statement yet.

### C. arq worker in Compose: recommendation (best practice)
Add a dedicated `worker` service rather than running jobs inside the API container:
- Same image as `backend`, `command: arq backend.worker.WorkerSettings`, same env, `depends_on` redis and postgres with `condition: service_healthy`, `restart: unless-stopped`, a `stop_grace_period` at least as long as the longest job, a healthcheck, no published ports.
- It must mount the same `uploads_data` volume as the API, otherwise jobs cannot read uploaded files.
- Set `USE_ARQ_QUEUE=true` on `backend` only when the worker exists; keep the default `false` for local dev.
- Set arq `max_jobs`, `job_timeout` and retry limits explicitly, and make `process_batch` idempotent so retries do not duplicate candidates. Scale later with `docker compose up --scale worker=N`.
- Why: the API stays responsive during heavy OCR/embedding ingestion, jobs survive API restarts (Redis-backed), and failures are retried. Needs approval before editing `docker-compose.yml`.

### D. Re-test after conflict resolution (owner's uncommitted working-tree fixes)
Environment as before; OpenSearch at `localhost:9200` is now up; Qdrant still pointed at a dead address on purpose (`.env` holds a cloud key).
**Result: 228 passed, 12 failed.** All 19 test files now collect.

| Failing test(s) | Symptom | Preliminary cause (hypothesis unless stated) |
|---|---|---|
| `test_requirement_history_and_notice.py` x3 | unchanged from Phase 1: `no_of_positions` default/validation; Fulfilled status 422 | tests stale vs. schema (`Optional[int]`, `ge=0`) and a status-needs-candidates rule |
| `test_requirement_status_and_email_history.py::test_ai_generation_is_personalized_and_requires_shortlist` (line ~176) | `set() == {candidate ids}` | assertion on recipients/shortlist; may depend on the conflict-merge outcome |
| `test_...::test_ai_generation_failure_is_reported_without_fallback[raise, unreachable, garbage, empty, placeholder]` x5 (line ~229) | rows returned where `[]` expected (rows carry `sendable: True`) | test expects no templated fallback when generation fails, but code returns rows. Merge outcome or product decision needed |
| `test_reviews.py::test_deleting_candidate_removes_comments_and_assignments` | `DELETE /api/candidates/{id}` returns **500** after about 2 s | real bug **or** environment: delete touches Qdrant, deliberately unreachable here. Re-run with Qdrant faked/reachable to separate; treat as potential defect until then |
| `test_roles.py::test_register_defaults_to_recruiter`, `test_bootstrap_admin_email_gets_admin` | registration returns **422** | registration validation likely changed (verify in `routers/auth.py`) |

None of the 12 were fixed (read-only).

### E. Root-folder review: what is likely removable (evidence-based; nothing deleted)

| File | Evidence | Verdict / confidence |
|---|---|---|
| `requirements.txt` | autogenerated by `uv export`; Dockerfile uses `uv sync --frozen`; only README mentions it as a pip fallback | redundant but harmless; keep or regenerate. Low removal value |
| `run-docker.bat` | referenced nowhere (`.sh` and `.ps1` are referenced in DOCKER.md) | **candidate, Medium** (owner confirm) |
| `run-docker.sh`, `run-docker.ps1`, `start-dgx-tunnel.sh` | referenced in README/DOCKER.md | keep |
| `model_capabilities.yaml` | header says it is an optional file for the GSD agent framework; no code references; listed in `.gitignore` yet tracked | **candidate, High** |
| `README.md`, `DOCKER.md`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `.gitignore`, `pyproject.toml`, `uv.lock` | core | keep |
| `PRODUCT.md`, `file-structure.md` | already deleted in the working tree by the owner (`PRODUCT.md` moved to `.impeccable/PRODUCT.md`) | in progress by owner |
| `backend/backend.zip`, `frontend/frontend.zip` (not root, but the largest junk) | stale source snapshots in tree (about 2 MB) | **candidate, High** after inspecting contents/dates |

Untracked/ignored root items (not in git; local cleanup only): `.agent/`, `.agents/`, `.gsd/`, `.gemini/`, `.claude/` (agent tooling), `.vscode/`, `.vite/` (stray cache at root), `.pytest_cache/`, `.venv/` (Linux 3.14 venv; `.venv-win` is the Windows one), `VERSION`, `command.md` (not referenced by code; owner to confirm), and runtime data `Camunda-resumes/`, `JD/`, `uploads/`, `logs/` (PII; never commit). `adapters/` and `scripts/validate-*`, `search_repo*`, `setup_search*` are agent-workflow tooling, not product code: Phase 4 review candidates, Medium.

### F. Updated unresolved questions
1. Approve restoring the fallback chain with the fixes in A, and decide the PII-egress policy?
2. Email generation: should a templated fallback exist when AI generation fails (tests say no)?
3. Candidate delete 500: real defect or Qdrant-unreachable artifact?
4. Registration 422: intended schema change?
5. Approve adding the arq `worker` service per C?
