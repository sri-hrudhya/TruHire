# Phase 3 — Frontend Dependency and Reachability Audit

Date: 2026-11-01. Branch `test`. Read-only: no frontend source, manifest or lockfile changed in this phase. Scratch scripts and build output lived outside the repo.

## 1. Entry points and route map (confirmed)
- `index.html` -> `src/main.jsx` -> `App.jsx` (`React.StrictMode`, `BrowserRouter`). Providers: Auth, Meta, Theme contexts. No lazy routes, no `React.lazy`, no dynamic `import()`: the whole app is one bundle (JS 419 kB / 126 kB gzip).
- Routes (`App.jsx`): `/login` (public); behind `ProtectedLayout`: `/ingestion`, `/ingestion/history`, `/requirements`, `/search`, `/email`, `/candidates/:id`, `/analytics`; redirects: `/` -> default route, `/job-descriptions` and `/positions` -> `/requirements`, `*` -> default route. The assistant panel (`TruHireAssistant`) is mounted in the layout.
- Pages (8): Analytics, Auth, CandidateDetail, Email, IngestionHistory, Ingestion, JobDescriptions, Search. All 8 are reachable from a route.
- State: React context + local state; no Redux/Zustand. API client: one axios instance (`lib/api.js`) with JWT interceptor, a custom caching adapter (`lib/requestCache.js`, per-path TTL and invalidation rules), and 401 -> login redirect. The streaming assistant call is the one exception: it uses `fetch` (`lib/assistantStream.js`), because axios cannot read a response while it arrives.

## 2. Graph method and limitations
- Script walked every `src/**/*.js|jsx|css`, resolved relative `import` / `export … from` / `import()` / CSS `@import`, and did a DFS from `main.jsx`. Exports were checked by whole-word search across src and tests. API calls were mapped by extracting every `api.<verb>(path)` from `lib/api.js` and comparing with decorators in `backend/routers/*.py`.
- Limits: no TypeScript or JS type information; class-name checks are text matches, so dynamically built names are only caught where the template string is visible; routes are matched by shape (`{x}` for ids), not by behaviour.

## 3. Reachability result
- 94 tracked frontend files; every source file is reachable from `main.jsx` **except two**:

| File | Evidence | Verdict | Confidence |
|---|---|---|---|
| `src/components/AIChatWindow.jsx` (105 lines) | imported nowhere (src, tests, docs); only its own definition matches the name; **imports `chatApi` from `lib/api.js`, which does not exist** (0 matches in api.js), and no `/chat` route exists in the backend | **Dead and broken.** Superseded by `TruHireAssistant.jsx`. Would fail to build if imported | **High** |
| `src/components/AIAuditPanel.jsx` (144 lines) | imported nowhere; but it is a working component bound to a live endpoint (`aiAuditApi.list` -> `GET /api/ai-audit`), and `requestCache.js` has a TTL rule for `/ai-audit` | **Disconnected feature**, not obsolete: the AI-audit admin view has no page or route. Possibly meant for an admin screen | **Medium** (product decision) |

- Unreferenced exports (src + tests): `LogoMark` (used inside its own file only), `RetentionModal`, `STATUS_MARKS`, `NOTICE_UNITS`, `RECENT_RESUME_DAYS`, `UNIT_DAYS`, `MAX_EXPERIENCE_YEARS`, `MAX_POSITIONS`, `RESUME_LINKED`, `statusRank`. Most are constants used inside their own module. **`RetentionModal`** is the interesting one: a modal with no importer while `retentionApi.cleanup` exists. **Low-Medium**, needs a look in Phase 4.
- API-client methods never called outside `api.js`: `demandApi.get`, `demandApi.listJds`, and (after this branch's streaming change) `assistantApi.send`. All three still match live backend routes. **Low** value to remove; `assistantApi.send` is now only a fallback path, since the panel streams.
- Dependencies: all 8 (5 runtime, 3 dev) are used. No lint, TypeScript, Tailwind, PostCSS or alias configuration exists.

## 4. API calls vs backend routes
- **Every frontend call matches a backend route** (0 mismatches; 52 client routes vs 70 backend routes).
- Backend routes with no call from `api.js` (candidates for Phase 4/5 review, not defects): `DELETE /candidates/{id}`, `POST /candidates/bulk-delete`, `DELETE /demands/{id}`, `POST /demands`, `PUT /demands/{id}`, `PUT /job-descriptions/{id}/demand`, `GET /job-descriptions/{id}`, `GET /search/state`, `DELETE /search/state`, `GET /ingest/batches`, `GET /ingest/index-status`, `POST /ingest/reindex`, `POST /ingest/reparse`, `GET /email/records/{id}`, `PATCH /users/{id}/role`, `POST /retention/cleanup` (called from `retentionApi` with a query string; false positive from my matcher). Some are admin or maintenance endpoints meant for curl/ops. **Security note for Phase 5:** destructive and admin routes (`reparse`, `reindex`, `bulk-delete`, `users/{id}/role`) exist without any UI; check each one's authorization.
- Streaming endpoint `POST /assistant/message/stream` is called only from `assistantStream.js` (fetch, not axios), so it appears in the matcher as uncalled.

## 5. Styles and assets
- CSS is plain global files imported per component, plus `index.css` which `@import`s `styles/{tokens,base,layout}.css`. All 10 CSS files are imported by something. Tokens support light/dark via `[data-theme]`.
- **Classes that never appear in JS:** `index.css`: `gap-4`, `text-lg`, `responsive-2col`, `page-header-subtitle`, `sidebar-nav-label`; `requirements.css`: `req-dek`, `req-filter`, `req-item(s)`, `req-layout`, `req-list`, `req-open`, `req-remove`, `landing-heading`, `info-card-facts-grid`, `info-card-label`, `is-selected`. **Medium** confidence that these are dead: they look like leftovers from an older requirements layout, but I haven't visually verified any removal.
- **Dynamically composed names (false positives, keep):** `history-{action}`, `match-score-{tone}`, `skill-{tone}`, `modal-{size}`, `notice-{type}`, `status-mark-{kind}`.
- Assets: `public/truviq-block-logo.png` is used by the navbar (added on this branch). **`public/Logo.png` is referenced nowhere** (src, index.html, docs): **Medium-High** candidate. Note `frontend/public/` is **untracked in git**; both files need committing, or the Docker build loses the Truviq logo.
- Fonts: loaded from Google Fonts in `index.html` (Public Sans, Source Serif 4). Runtime dependency on an external CDN; matters for air-gapped or on-prem DGX deployments (Phase 7). The favicon is an inline SVG data URI, not the brand mark.

## 6. Build, test and tooling-only files
- **Tests (Node, no framework):** 7 files wired into `npm test` (requestCache, categories, meta, categoryRow, sections, jdFormat, assistantStream); 44 assertions, all passing. They cover `lib/` and `config/` only: **no component, page, context or hook is unit-tested**.
- `tests/e2e/search-modes.spec.mjs`: Playwright (`playwright-core`) script with mocked API, run by hand against a dev server; not in `npm test`, no CI, uses the ignored `tests/e2e/screenshots/`. `playwright-core` is a devDependency used only here.
- `vite.config.js`: dev proxy `/api` -> backend; **dev throws if neither `VITE_BACKEND_URL` nor `VITE_BACKEND_PORT` is set**; no aliases; build has no chunk-splitting.
- `Dockerfile` (node 20 -> nginx 1.27), `nginx.conf`: SPA fallback, 1-year immutable cache for `/assets/`, `/api/` proxy with **`proxy_buffering off`** and 300 s read timeout. This is what lets the new assistant streaming reach the browser in chunks (the backend also sends `X-Accel-Buffering: no`). `Connection "upgrade"` is set unconditionally on `/api/`; harmless but unusual (hypothesis: should be conditional on `$http_upgrade`).
- `DESIGN.md`, `.dockerignore`, `.gitignore`: documentation and build hygiene. No `import.meta.env` usage anywhere in src: runtime configuration is constants in `config/env.js` and the relative `/api` path.

## 7. Dynamic-reference caveats
- Class names built from template strings (above) keep many "unused" classes alive.
- Route table, nav items and status labels are data-driven (`config/`, `lib/meta.js`, `/api/meta`); anything keyed by backend enums (statuses, categories) cannot be proven unused from the frontend alone.
- `StatusMark` and `statusMarks.js`: `STATUS_MARKS` is exported but unreferenced, `StatusMark.jsx` is used; check whether the table is duplicated.

## 8. Commands and checks run
- `git ls-files` classification, `npm test` (44/44 pass), `vite build` to a scratch directory (passes).
- Python AST-free text scripts: import/CSS graph (`fgraph.py`), export usage, API-method usage, dependency usage, asset and CSS reference scan (`fcheck.py`), API-route comparison (`apimap.py`). All read-only, outside the repo.
- Targeted reads: `App.jsx`, `main.jsx`, `vite.config.js`, `nginx.conf`, `Dockerfile`, `index.html`, `api.js` sections, both unreachable components.

## 9. Unresolved questions (for you)
1. `AIChatWindow.jsx`: confirm it is the old assistant and can go (broken import, no importer).
2. `AIAuditPanel.jsx`: should the AI-audit view get an admin page, or be removed? It is a ready, working component.
3. `RetentionModal` and the maintenance routes (`reindex`, `reparse`, `bulk-delete`, `users/{id}/role`): intended as ops-only, or unfinished UI?
4. `public/Logo.png`: used anywhere outside the repo (e.g. docs)?
5. Should `frontend/public/` be committed now (needed for the Truviq logo)?
6. Should Google Fonts be self-hosted for on-prem use?

## 10. Confirmation
No frontend files were changed in this phase. Only this report was created. (The working tree still holds the earlier, uncommitted implementation work on branch `test`; none of it was modified here.)
