# TruHire

TruHire is an AI-powered hiring platform that combines hybrid candidate search
(semantic + lexical), job-description-aware scoring, and a lightweight local
decision layer to help recruiting teams find and evaluate candidates faster —
with fewer, cheaper calls to a large language model.

## Key Capabilities

- **Hybrid candidate search** — semantic vector search (Qdrant) fused with
  lexical/BM25 search (OpenSearch) via weighted reciprocal-rank fusion.
- **JD-aware scoring** — deterministic scoring based on skill coverage,
  experience, and education fit against a job description, blended with a
  fast local relevance judgment for reranking.
- **Local decision layer** — a compact, non-autoregressive decision model runs
  on-box for reranking, chat-intent routing, and output guardrails, so the
  large language model is only invoked when a confident answer actually
  requires one.
- **Conversational assistant** — persistent, context-aware chat scoped to a
  candidate or a job description, backed by retrieval-augmented generation.
- **Guardrails** — every model-generated summary and chat reply is checked
  for groundedness against its source text and for unsafe/biased language
  before it reaches a user, with a deterministic fallback if a check fails.
- **PII-aware pipeline** — resumes and job descriptions are redacted before
  being sent to any embedding or generation endpoint.
- **Persistent state** — search filters, results, and chat conversations
  survive navigation, backed by SQL as the source of truth.

## Architecture

```
frontend (React + Vite)
        │  /api
        ▼
backend (FastAPI)
        │
        ├── PostgreSQL              — users, candidates, requirements, matches, chat, email, AI audit trail
        ├── Qdrant                  — candidate embedding vectors (semantic search)
        ├── OpenSearch              — lexical/BM25 index (keyword search)
        ├── LLM inference endpoint  — OpenAI-compatible chat + embeddings
        └── Local decision model    — reranking, chat routing, guardrails
```

The backend talks to Qdrant, OpenSearch, and the LLM endpoint purely over
configuration (URLs and credentials in `.env`) — none of these are assumed to
run on any particular host or port. Point them at whatever infrastructure you
have available.

## Prerequisites

- Python 3.13+ (managed with `uv`)
- PostgreSQL 14+
- Node.js 18+
- A running Qdrant instance
- A running OpenSearch instance (optional — used for lexical retrieval)
- An OpenAI-compatible LLM inference endpoint (chat + embeddings)

## Getting Started

### 1. Configure the environment

Copy the example environment file and fill in your own values:

```bash
cp .env.example .env   # repository root; settings are read from the working directory
```

At minimum, set:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL, e.g. `postgresql+psycopg://user:pass@localhost:5432/truhire` (URL-encode `@` in passwords as `%40`) |
| `SECRET_KEY` | JWT signing key — set a long random value |
| `VLLM_BASE_URL` | Your OpenAI-compatible LLM/embedding endpoint |
| `VLLM_MODEL` | The chat/generation model served at that endpoint |
| `VLLM_EMBEDDING_MODEL` | The embedding model served at that endpoint (must be a real embedding model, not a chat-only model) |
| `QDRANT_URL` | Your Qdrant instance |
| `OPENSEARCH_URL` | Your OpenSearch instance |
| `LAYA_ENABLED` | Enables the local decision layer (falls back to LLM-only behavior if disabled or unavailable) |

None of these need to point at `localhost` — configure them for wherever your
inference and vector infrastructure actually runs.

### 2. Run the backend

From the repository root (imports are rooted here, not inside `backend/`):

```bash
uv sync                      # or: python -m venv .venv && pip install -r requirements.txt
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port <your-chosen-port>
```

Tables are created on first start. To move an existing SQLite database
(`truhire.db`) into PostgreSQL, run once:

```bash
uv run python -m backend.scripts.migrate_sqlite_to_postgres --source sqlite:///./truhire.db
```

It copies every table in one transaction and verifies row counts; the SQLite
file is left untouched.

Health check: `GET /api/health`.

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend proxies `/api` to the backend — make sure the
backend port matches the proxy target configured in `frontend/vite.config.js`.

### 4. Index existing resumes

If you change the embedding model or the Qdrant collection, re-embed existing
candidates (runs in the background, returns 202):

```
POST /api/ingest/reindex                     # everything
POST /api/ingest/reindex?missing_only=true   # only resumes missing from the indexes
```

Uploaded resumes and requirement files are never served statically; they are
streamed to logged-in users via `GET /api/candidates/{id}/resume` and
`GET /api/job-descriptions/{id}/file`.

### 5. AI governance

- **Guardrails** (`GUARDRAILS_ENFORCE=true`): search summaries, chat replies, JD
  summaries and candidate emails are checked for groundedness and safety; output
  that can't be verified (including when Laya is unavailable) is replaced by a
  deterministic fallback or blocked. Emails can't contain links or contact
  details that aren't in the requirement or company settings.
- **Prompt-injection screening**: resumes with hidden (white, tiny, invisible,
  off-page) or embedded instructions aimed at an AI are rejected at upload.
  Re-screen stored resumes with
  `uv run python -m backend.scripts.scan_resume_injections` (dry run; add
  `--delete` to remove flagged candidates).
- **AI audit trail**: every LLM/Laya call, guardrail verdict and screening
  decision is recorded (PII-redacted previews, tokens, latency, user, trace id)
  and visible on the Analytics page / `GET /api/ai-audit`.

## The Decision Layer

Rather than routing every judgment call (rerank a candidate, decide chat
intent, verify a generated summary) through the LLM, TruHire first asks a
small, local decision model a typed question — a choice, a score, or a
yes/no — and only escalates to the LLM when that model isn't confident
enough. This cuts LLM calls substantially on the hot paths (JD-scored search
used to call the LLM once per candidate in the retrieval pool; it now calls
the LLM only for the candidates actually returned to the user) without
changing the underlying deterministic scoring formulas.

## Project Structure

```
backend/
  routers/        # FastAPI route handlers
  services/        # Business logic: search, scoring, decision layer, guardrails,
                    # LLM/embedding client, PII redaction, caching
  models.py         # SQLAlchemy models
  config.py         # Environment-driven settings
frontend/
  src/              # React application
```

## Troubleshooting

- **Ingest/search fails with "No embedding model configured"** — set
  `VLLM_EMBEDDING_MODEL` (or `EMBEDDING_MODEL`) to a real embedding model
  served by your LLM endpoint; a chat-only model will not work.
- **Frontend requests fail with connection errors** — confirm the backend is
  running and that its port matches `frontend/vite.config.js`'s proxy target.
- **Stale or incompatible vectors after changing the embedding model** — use a
  fresh Qdrant collection (or clear the existing one) and run
  `POST /api/ingest/reindex`.
