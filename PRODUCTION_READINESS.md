# Production Readiness

What's done, and what's genuinely still needed before a real deployment.

## Done this pass

- **Config hardening**: `VLLM_BASE_URL`, `QDRANT_URL`, `OPENSEARCH_URL` are required
  settings with no in-code defaults — the app fails fast at startup with a clear error
  if `.env` doesn't provide them, instead of silently running with an exposed or
  misleading default.
- **Backend reorganized**: `backend/services/` split into `llm/`, `retrieval/`,
  `ingestion/`, `common/` by responsibility (was a flat 17-file directory).
- **Rate limiting** (`slowapi`): tighter limits on auth (login/register) and resume
  upload, a looser default elsewhere. Configurable via `RATE_LIMIT_*` in `.env`.
- **Ingestion made batch-efficient**: embedding generation, Qdrant upsert, and
  OpenSearch indexing each run once per upload batch instead of once per resume.
  Fixed a real bug in the process: duplicate/empty-text files were skipping the
  progress-tracking commit entirely, so batch status silently never reflected them.
- **Scalable queue architecture, opt-in**: ingestion still defaults to FastAPI
  `BackgroundTasks` (zero extra infra) for local dev. Setting `REDIS_URL` switches it
  to an `arq`-backed queue processed by a separate `backend/worker.py` process — for
  when you actually deploy this and want ingestion off the API server.
- **UI**: removed the fake "service up" status dot; replaced the indigo/violet color
  scheme with a neutral blue in both themes; default theme flipped to light; added a
  reusable utility-class layer and converted the shared Navbar/Sidebar/chat window plus
  page headers and the Analytics KPI grid off inline styles.
- **Dead code removed**: unused functions across `vllm.py`/`pii.py`, unused config
  fields, a stray `index.html`, duplicate `requirements.txt` (now regenerated from
  `pyproject.toml` via `uv export` instead of hand-maintained separately).

## Explicitly out of scope (by your choice)

- **Automated tests** — none added; you're testing manually.

## Still genuinely needed before a real deployment

1. **Schema migrations**: `database.py::ensure_schema()` hand-rolls `ALTER TABLE`
   statements. Fine solo; needs Alembic (or similar) for a team/multiple environments.
2. **Containerization**: no `Dockerfile`/`docker-compose.yml` for the app itself (only
   local infra has one). Needed for any real deployment target.
3. **Secrets management**: currently a local `.env`. A real deployment needs a secrets
   manager, not a plain file.
4. **CI**: no automated lint/test/build gate on changes.
5. **CORS**: `CORS_ORIGINS` in `config.py` is hardcoded to localhost dev ports — needs
   real production origins before going live.
6. **Structured logging**: currently a mix of `print()` and one tracing middleware
   (`observability.py`'s trace-ID plumbing) — worth consolidating.
7. **Retry/circuit-breaker**: external vLLM/Qdrant/OpenSearch calls degrade gracefully
   today (confirmed working under real outages this session) but don't retry
   transient failures.
8. **Remaining frontend inline-style conversion**: the shared components (Navbar,
   Sidebar, chat window), page headers, and the Analytics KPI grid are converted to
   CSS classes; the bulk of each page's own body content (search results, JD list,
   candidate detail, auth form) still uses inline `style={{}}` extensively. Purely a
   maintainability/consistency concern, not a functional one — a good next pass.
