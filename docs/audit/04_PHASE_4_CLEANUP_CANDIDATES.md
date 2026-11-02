# Phase 4 — Unused Code, Duplication and Dependency Audit

Date: 2026-11-01. Branch `test` @ `9610ea6`. **Read-only: no code, manifest or lockfile changed.** Tools were run through `uvx`/`npm audit` (nothing installed into the project). Vulnerability lookups sent only package names and versions to the public advisory databases (PyPI/OSV via pip-audit, npm registry); no repository code left the machine.

## 1. Candidate cleanup table
Confidence: High = multiple independent signals; Medium = plausible, needs a person; Low = keep pending investigation.

| # | Candidate | Evidence (independent signals) | Action | Risk | Confidence |
|---|---|---|---|---|---|
| C1 | `backend/routers/ingestion.py:20,22` imports `generate_embedding`, `index_candidate` | ruff F401 + vulture (90%); name appears once in the file; not re-exported (`__all__` absent); no test patches `ingestion.index_candidate` | Remove 2 unused imports | None (unused names) | **High** |
| C2 | `backend/config.py:2` `pydantic.Field`; `backend/routers/assistant.py:4` `typing.Any`; `backend/main.py:3` duplicate `import logging` (also at line 1) | ruff F401 / F811 | Remove | None | **High** |
| C3 | `backend/services/common/cache.py:161,167` `cache_user_session`, `get_cached_user_session` | zero callers (Phase 2 scan, re-checked); owner confirmed Redis already covers sessions; auth is stateless JWT | Remove both | Low | **High** |
| C4 | `backend/services/llm/laya_service.py:184,194` `ask_choice`, `ask_score_batch` | zero callers; owner says scoring uses reranker + embeddings | Remove | Low; **hold until the Laya discussion** | **Medium-High** |
| C5 | `backend/services/retrieval/qdrant.py:165` `upsert_candidate` | zero callers (batch upsert is used); owner has not commented | Keep pending owner | Low | **Medium** |
| C6 | `backend/routers/demands.py:139` variable `detach_jds`; `backend/services/ingestion/injection_screen.py:163` variable `font_dict` | vulture 100% on unused local/parameter | Inspect; likely dead assignments | Low | **Medium** |
| C7 | Frontend CSS classes with no reference in JS: `gap-4`, `text-lg`, `responsive-2col`, `page-header-subtitle`, `sidebar-nav-label` (`index.css`); `req-dek`, `req-filter`, `req-item(s)`, `req-layout`, `req-list`, `req-open`, `req-remove`, `landing-heading`, `info-card-facts-grid`, `info-card-label`, `is-selected` (`requirements.css`) | text search over all JS/HTML; none match dynamic template names (`history-*`, `match-score-*`, `skill-*`, `modal-*`, `notice-*`, `status-mark-*` are kept) | Remove after a visual check | Low-Medium (a class could be set from data) | **Medium** |
| C8 | `frontend/src/components/AIChatWindow.jsx` | **already deleted on this branch** (nothing imported it; imported nonexistent `chatApi`) | Done | — | High |
| C9 | `frontend/src/api` methods `demandApi.get`, `demandApi.listJds`, `assistantApi.send` | no callers outside `api.js`; routes still exist | Keep (tiny; `send` is the non-stream fallback) | Low | **Low** |
| C10 | Tooling that is not product code: `adapters/` (3 files), `scripts/validate-*` (10 files), `scripts/search_repo.*`, `scripts/setup_search.*` (4 files) | `adapters/*` point at `PROJECT_RULES.md` (gitignored, absent from the repo); `validate-*` check `.agents/agents/` etc. (GSD agent framework, gitignored); no code, compose, Docker or README references except each other | Owner decision: move to a separate tooling repo or delete | None for the app | **Medium** |
| C11 | `docs/truhire-current-workflow.mmd/.svg` | referenced by nothing; may be stale | Owner decision | None | **Low** |
| C12 | `.impeccable/surfaces/frontend-src-pages-jobdescriptionspage-jsx.md` | design-tool context only | Keep if you use Impeccable | None | **Low** |
| C13 | `frontend/src/components/AIAuditPanel.jsx`, `RetentionModal` (`RequirementModals.jsx:34`) | disconnected but working UI bound to live endpoints (see Phase 3) | **Do not delete**: decide to wire or remove | — | Product decision |

Not candidates, though they look like it: `backend/evaluation/`, `backend/scripts/*` (documented CLIs, tested); the three cloud provider modules (now wired into the fallback chain); `python-multipart`, `uvicorn`, `psycopg` (no `import` line, but FastAPI uploads, the container command and the SQLAlchemy driver need them).

## 2. Static-analysis results (ruff F/B/E7/E9/SIM, vulture >=80%)
- **F401 unused imports: 10** (C1, C2 above, rest in tests). **F811 redefinitions: 51**, all but one in tests: `from test_location_role_filters import env` re-imported fixtures that pytest sees as redefined arguments; this is the intended pytest idiom, noise. The one real case is `main.py` `logging` (C2).
- **ruff "invalid-syntax" at `services/retrieval/search.py:433`**: the line is `match.match_score = ...; match.score_breakdown = ...`. It parses and runs (tests pass); ruff trips over `match` being a soft keyword. **False positive**; but the semicolon-chained line is style debt (see maintainability).
- B008 x141 (`Depends(...)` in defaults, the FastAPI norm: ignore). E702/E701 x36 (semicolons / one-line `if`), PLW0603 x21 (`global` state: caches, breaker, writer queue), B023 x15, B905 x6 (`zip()` without `strict`), B904 x5 (`raise` inside `except` without `from`), S110 x3 (bare `except: pass`). These are maintainability items, not defects. The ones worth a look: **S110 (silent swallow)** and **B904**, since both hide error causes.
- vulture 100% hits on `cls` (pydantic validators) and `admin`/`ctx` (FastAPI dependency / arq context parameters) are framework conventions: ignore.
- No `print()` debugging in app code; `print` only in the two CLI scripts (intended). No `console.log`/`debugger` in the frontend. Only one TODO in the backend: see section 5.
- **No linter or formatter is configured in the repo** (no ruff/mypy/eslint config), so these findings will recur. Recommended in Phase 9: add a minimal `ruff` config and a CI check.

## 3. Dependency findings
### Python (`pyproject.toml`, `uv.lock`; 20 direct deps + 1 optional `laya`)
- Every direct dependency is used (import map in backend/scripts, or required by framework/runtime). No removal candidates. `numpy` is imported once (OCR path) and is also pulled by `fastembed`; keep.
- Dev group has only `pytest`. `tests/test_jd_upload_and_retention.py` imports `PIL` and `docx` (both come in transitively via runtime deps; fine).
- **Reproducibility:** `uv.lock` is committed and the Docker build uses it. `requirements.txt` is regenerated from it and matches (verified in Phase 2 work). The `laya` extra is **not** in `requirements.txt` or the image (owner discussion pending).
- **Version drift:** many locked packages are behind (e.g. fastapi 0.142.1 vs 0.162.0, fastembed 0.8.1 vs 0.9.1, laya 0.3.22 vs 0.4.20). Not an issue by itself.
- **Known vulnerabilities (pip-audit on the locked runtime set incl. `laya`): 83 advisories in 10 packages.** Triage by whether the app reaches the vulnerable code:

| Package (locked) | Advisories | Reachable here? | Fix |
|---|---|---|---|
| **pypdf 6.19.0** | 18 (infinite loops, memory use on crafted PDFs; the worst need `PdfWriter`/outline APIs) | **Yes: resumes and JDs are untrusted PDFs parsed by `parsing.py` and `injection_screen.py`**. Reading paths (stream filters, memory) are the relevant ones | 6.21.4 (fixes all) |
| **pillow 12.3.0** | 39 (decoder over-reads, TIFF use-after-free, filters) | **Yes: uploaded images go through Pillow via the OCR/parse path** | 13.0.0 (major) |
| **python-jose 3.5.0** | 1 (HMAC init accepts public-key-shaped secrets) | **No**: app uses `HS256` with a shared `SECRET_KEY` and a pinned `algorithms=[...]`; the issue needs asymmetric keys. But python-jose has **no fix** and is poorly maintained | Plan a move to PyJWT/authlib (Medium) |
| **ecdsa 0.19.2** (via python-jose) | 1 (Minerva timing, P-256) | No: HS256 never calls ecdsa | none upstream; disappears with python-jose |
| **filelock 4.0.7** | 14 (lock-file handling, mostly Windows) | Low: transitive of the model downloader; Linux container | 4.2.6 |
| **pyasn1 0.6.4** | 4 (quadratic CPU on crafted BER) | Low: transitive of jose/rsa; no ASN.1 from users | 0.6.5 |
| certifi 2026.7.22 | 2 (CA bundle includes a distrusted root) | Yes, applies to outbound HTTPS (cloud LLMs, Qdrant) | 2026.10.18 |
| setuptools 84.0.0, dnspython 2.8.0, opentelemetry-api 1.45.0 | 1 each | Low | patch bumps |

### Frontend (`package.json`, lockfile)
- All 8 direct deps used. `npm audit --omit=dev`: **3 findings.** `react-router` / `react-router-dom` (moderate, range 6.0.0 to 7.17.0; fix is a **semver-major jump to 7.18.5**, so retest the router) and `follow-redirects` (high, transitive of `axios`; used by Node, not by the browser bundle, so practical risk is low; `npm audit fix` resolves it without a major change).
- I added three `@fontsource/*` packages on this branch (self-hosted fonts); they are data-only packages with no advisories reported.
- `playwright-core` is dev-only (used by the manual e2e script). `package-lock.json` is committed; the Docker build runs `npm ci || npm install`: the `|| npm install` fallback silently ignores a stale lockfile (**reproducibility risk**, Low).

## 4. Duplication and maintainability findings
- **Same name, different behaviour (not duplicates):** `_clean_locations` (JD form vs search filter), `_headers` (vLLM vs Qdrant), `_serialize`, `record`, `main`, `_get_model`, embeddings wrappers (`ai_service` -> `local_embeddings`/`vllm` by design).
- **Real duplication:** `frontend` `formatDateTime` exists in `components/EmailComposer.jsx:33` and `lib/requirements.js:19`; `errorText` exists in `hooks/useRequirements.js:11` and `pages/EmailPage.jsx:8` with slightly different bodies. **Medium**: consolidate into `lib/`, check outputs match first. `PAGE` constants are separate page sizes (not duplicates).
- Provider modules (`gemini/groq/openrouter`) are now thin wrappers over one shared helper; this removed the near-copy-paste they had before.
- **Style debt:** 36 semicolon-chained or one-line statements (e.g. `search.py:433`), 21 module-level `global` states, no type checking. Several 600+ line files (`vllm.py` ~690, `job_descriptions.py` ~1000, `useRequirements.js`). Not defects; they raise change risk.
- **Error handling:** 3 bare `except: pass` (S110) and 5 `raise` without `from` (B904) hide root causes; list the exact lines in Phase 9 if approved.
- **Shared test imports:** five test files import fixtures from `test_location_role_filters.py` and `test_roles.py` instead of `conftest.py`; this is why one conflict marker broke 7 files. Moving the fixtures to `conftest.py` is a cheap robustness win.

## 5. Items requiring product or human confirmation
1. **Laya** (`ask_choice`, `ask_score_batch`, Docker extra): deferred by you.
2. `adapters/`, `scripts/validate-*`, `search_repo`, `setup_search` (C10): keep, move out, or delete?
3. `AIAuditPanel.jsx` and `RetentionModal`: wire into an admin page, or remove?
4. `qdrant.upsert_candidate` (C5): any planned single-upsert path?
5. Remove the ~16 dead CSS classes (C7) after a visual check?
6. python-jose: approve migrating auth to PyJWT (no upstream fix, sole user of ecdsa/pyasn1)?
7. Version upgrade scope: at minimum pypdf, pillow, certifi, react-router; **needs a regression run**. Do it as its own change.
8. `docs/truhire-current-workflow.*` still accurate?
9. **Security finding found in passing (belongs to Phase 5):** `backend/routers/ai_audit.py:49` `# TODO(roles): restrict to admins`: any logged-in user can list AI audit events (prompt/output previews). Roles now exist (`require_role` in `auth.py`, used by `users.py`), so the TODO is stale.

## 6. Validation evidence and limitations
- Commands: `ruff check` (F, B, E7, E9, T20, PLW0603, ERA001, S110, S112, SIM), `ruff --statistics`, `vulture backend --min-confidence 80`, `pip-audit -r <uv export, locked, incl. laya> --no-deps`, `npm audit --omit=dev`, import-to-package map script, whole-word reference scans, Phase 2 and 3 graph scripts. All read-only.
- Limits: vulture/ruff cannot see FastAPI `Depends`, pydantic validators, SQLAlchemy models or `getattr` dispatch; reachability of vulnerable library code is by reading call sites, not by exploit testing; `pip-audit` reflects the lockfile, not the container image; no coverage tool exists, so "untested" is only a signal; `deptry` could not map package names without an installed environment, so the import map was done manually.
- Test baseline unchanged: 283 backend tests and 44 frontend assertions pass.

## 7. Confirmation
No application code, manifests or lockfiles were changed. Only this report was created.
