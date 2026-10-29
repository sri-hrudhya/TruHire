# 🐳 Running TruHire with Docker

This guide explains how to run the entire TruHire stack (Frontend, Backend, PostgreSQL, Redis, Qdrant, OpenSearch) in Docker containers with a single command.

---

## ⚡ Quickstart

### 1. Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running (macOS, Windows, or Linux).
- Docker Compose v2+ (included with modern Docker Desktop).

### 2. Configure Environment
Copy the Docker environment template:
```bash
cp .env.docker.example .env
```
*(On Windows Command Prompt: `copy .env.docker.example .env`)*

Open `.env` and set at least one LLM provider key:
- **Groq** (fast & free tier): set `GROQ_API_KEY=gsk_...` from [console.groq.com](https://console.groq.com/keys)
- **OpenRouter**: set `OPENROUTER_API_KEY_1=sk-or-v1-...` from [openrouter.ai](https://openrouter.ai/keys)
- **Gemini**: set `GEMINI_API_KEY_1=...` from [aistudio.google.com](https://aistudio.google.com/)
- **Local Ollama**: set `VLLM_BASE_URL=http://host.docker.internal:11434/v1` and `VLLM_MODEL=llama3.1:latest`

> **Note on Embeddings:** Local embeddings (`BAAI/bge-base-en-v1.5`) run in-process inside the backend container using `fastembed`. No external embedding API key is needed!

> **Note on Laya:** Laya is disabled by default in Docker because its optional Torch dependency downloads several gigabytes of CUDA packages. Set `LAYA_ENABLED=true` only when you have installed the `laya` extra and want to run the local decision model.

### 3. Start the Platform
Run the startup script:

**Linux / macOS / WSL:**
```bash
chmod +x run-docker.sh
./run-docker.sh
```

**Windows (PowerShell):**
```powershell
.\run-docker.ps1
```

**Or directly via Docker Compose:**
```bash
docker compose up --build -d
```

---

## 🌐 Accessing the Services

Once all containers are up:

| Service | URL | Description |
|---|---|---|
| **Web UI** | [http://localhost:3999](http://localhost:3999) | Main React Web Application |
| **Backend API Docs** | [http://localhost:3999/docs](http://localhost:3999/docs) | FastAPI Interactive Swagger UI |
| **Backend Direct** | [http://localhost:8999](http://localhost:8999) | Direct Backend HTTP Port |
| **OpenSearch Dashboards** | [http://localhost:5601](http://localhost:5601) | Search Index Explorer |
| **Qdrant Vector DB** | [http://localhost:6333](http://localhost:6333) | Vector DB REST API |
| **PostgreSQL** | `localhost:5432` | DB: `truhire`, User: `truhire` |

---

## 🏗️ Architecture & Containers

```
                       Browser (localhost:3999)
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │   truhire-frontend    │ (Nginx)
                     │  - Serves React SPA   │
                     │  - Proxies /api/*     │
                     └───────────┬───────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │    truhire-backend    │ (FastAPI)
                     └─────┬───┬───┬───┬─────┘
           ┌───────────────┘   │   │   └───────────────┐
           ▼                   ▼   ▼                   ▼
    ┌─────────────┐     ┌───────────┐     ┌────────────────┐
    │  PostgreSQL │     │   Redis   │     │ Qdrant Vector  │
    │  (Relational│     │ (Cache &  │     │   (Semantic    │
    │    Data)    │     │  Queues)  │     │    Search)     │
    └─────────────┘     └───────────┘     └────────────────┘
                               │
                               ▼
                        ┌─────────────┐
                        │ OpenSearch  │
                        │ (BM25 /     │
                        │  Lexical)   │
                        └─────────────┘
```

---

## 🛠️ Management & Commands

### View Live Logs
```bash
# All services
docker compose logs -f

# Backend logs only
docker compose logs -f backend

# Frontend logs only
docker compose logs -f frontend
```

### Stop the Containers
```bash
docker compose down
```

### Stop and Wipe All Data Volumes (Clean Slate)
```bash
docker compose down -v
```

### Rebuild After Code Changes
```bash
docker compose up --build -d
```

### Run Commands Inside the Backend Container
```bash
# Open interactive shell in backend
docker compose exec backend bash

# Run tests inside container
docker compose exec backend pytest
```

---

## ❓ Troubleshooting

### 1. Port Conflicts (e.g. 5432 or 6379 already in use)
If you already run a local PostgreSQL or Redis on your host, you can customize the host-mapped ports in `.env`:
```env
POSTGRES_PORT=5433
REDIS_PORT=6380
FRONTEND_PORT=3999
```
The internal container network will continue to communicate properly.

### 2. OpenSearch Memory Limits on Linux
If OpenSearch fails to start on Linux with `max virtual memory areas vm.max_map_count [65530] is too low`, run:
```bash
sudo sysctl -w vm.max_map_count=262144
```
To make it permanent, add `vm.max_map_count=262144` to `/etc/sysctl.conf`.

### 3. Model Downloads & Persistent Cache
On first startup, the backend downloads the lightweight sentence embedding model (`bge-base-en-v1.5`) and reranker model into the persistent volume `model_cache`. These are cached permanently so subsequent restarts happen in ~5 seconds.
