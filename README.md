# TruHire — Full-Stack AI Hiring Platform

TruHire is an enterprise AI-powered recruitment platform designed for Talent Acquisition (TA) and HR teams to ingest resumes in bulk, define and version job descriptions, run natural language and hybrid semantic searches across a decoupled shared candidate pool, and review aggregate talent analytics—without ever listing thousands of candidates in an unbounded DOM.

---

## 🌟 Key Architecture & Highlights

- **Decoupled Shared Candidate Pool**: Candidates are not owned by any single position (`position_id` is nullable). Any candidate can be evaluated against any number of versioned Job Descriptions via `CandidateMatch`.
- **4 Core Top-Level Sections**:
  1. **Resume Ingestion (`/ingestion`)**: Dedicated multi-file bulk upload with drag-and-drop, asynchronous background parsing (`pypdf`), SHA-256 deduplication, live progress counters, and error logs.
  2. **Job Descriptions (`/job-descriptions`)**: Flat section to create, view, edit (bumps `jd_version`), and summarize JDs using LLM. (No candidate tables or applicant tracking here).
  3. **Candidate Search (`/search`)**: Unified search across the entire pool with natural-language modifier intent ("and/also/too" appends filters, "only/just/instead" replaces), removable filter chips, optional JD selection for candidate scoring with citations, and **strict top-N pagination** (default 20, max 100).
  4. **Analytics (`/analytics`)**: Aggregate distributions (top skills, experience buckets, match score distribution for chosen JD, ingestion velocity over time, recruitment status funnel) without rendering unbounded lists.
- **Privacy First (PII Redaction)**: Automated PII redaction runs **before** any text is passed to embeddings or external LLMs.
- **AI Orchestration**: Groq primary (`llama-3.1-8b-instant`) with automatic fallback (`llama-3.3-70b-versatile`), OpenRouter support, optional Gemini integration, and deterministic offline mock fallbacks.
- **OpenSearch Vector Search Dual-Mode**: Seamlessly interfaces with live OpenSearch clusters via KNN vector mapping, and automatically falls back to an embedded in-memory cosine similarity vector store for zero-config local development.
- **Frontend Design System**: Built with React + Vite, global design tokens in `src/index.css` supporting light and dark themes, responsive layout, and an interactive RAG Copilot (`AIChatWindow`).

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### 1. Backend Setup

```powershell
# Clone or navigate to repository
cd c:\Users\srihr\OneDrive\Desktop\TruHire

# Install dependencies (if not already installed)
pip install -r requirements.txt

# Run pytest test suite
python -m pytest backend/tests -v

# Start the FastAPI server
python -m uvicorn backend.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive OpenAPI documentation is at `http://localhost:8000/docs`.

### 2. Frontend Setup

```powershell
cd frontend

# Install dependencies
npm install

# Build production assets
npm run build

# Start Vite development server
npm run dev
```

The frontend will run at `http://localhost:5173`.

---

## 🐳 Docker Deployment

To spin up OpenSearch, OpenSearch Dashboards, and the TruHire backend with a single command:

```powershell
docker-compose up --build
```

- **TruHire Backend**: `http://localhost:8000`
- **OpenSearch Node**: `http://localhost:9200`
- **OpenSearch Dashboards**: `http://localhost:5601`

---

## 🧪 Pytest Test Suite

The test suite covers all platform capabilities:
- `test_auth.py`: JWT auth, password hashing, token validation.
- `test_pii.py`: PII detection & redaction safeguards.
- `test_scoring.py`: Hybrid scoring formula, weights, penalties.
- `test_parsing.py`: Resume structure extraction.
- `test_jd_versioning.py`: Automatic `jd_version` bumping on text edit and summarization.
- `test_ingestion.py`: Asynchronous batch upload, SHA-256 duplicate detection, error logging.
- `test_search.py`: Modifier words parsing ("and" vs "only"), candidate scoring against selected JD, top-N limit enforcement.
- `test_analytics.py`: Strictly aggregated metrics and conversion funnel.
- `test_caching.py`: In-memory query caching and TTL expiry.
- `test_e2e_flow.py`: Complete end-to-end recruitment journey.

To run tests:
```powershell
python -m pytest backend/tests -v
```

---

## 🛡️ Hybrid Scoring Formula

$$\text{Match Score} = (W_{\text{sem}} \times S_{\text{sem}}) + (W_{\text{skill}} \times S_{\text{skill}}) + S_{\text{base}} - P_{\text{exp}} - P_{\text{edu}}$$

- $W_{\text{sem}} = 0.45$: Semantic vector similarity between candidate profile and JD.
- $W_{\text{skill}} = 0.35$: Jaccard / coverage ratio of required technical skills.
- $S_{\text{base}} = 0.20$: Baseline candidate qualification score.
- $P_{\text{exp}} = 0.10$: Proportional experience penalty when candidate has fewer years than stated in the JD.
- $P_{\text{edu}} = 0.05$: Education penalty if degree requirements are unsatisfied.
- Output normalized to $0 - 100\%$.
