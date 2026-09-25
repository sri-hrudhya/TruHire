# TruHire — RAG Persistence & Hybrid Ranking Fix

This archive contains the updated backend and frontend source.

Main fixes:
1. Persistent search state per user — query, filters, selected JD, Top-N, retrieval telemetry, and results survive candidate navigation.
2. Persistent chat conversations — the UI restores candidate/JD conversations and the backend uses SQL as the source of truth for message history.
3. Real DGX/vLLM embeddings with no mock fallback.
4. Qdrant vector-dimension validation to prevent incompatible embeddings.
5. Correct hybrid retrieval: Qdrant semantic cosine + OpenSearch BM25, fused with weighted RRF.
6. JD-aware re-ranking using actual retrieval quality, JD skill coverage, experience, and education signals.
7. Explicit `POST /api/ingest/reindex-embeddings` for existing resumes.

## Setup

Configure the backend `.env` from `backend/.env.example`.

If DGX/vLLM and Qdrant are accessed through the existing SSH tunnel:

```bash
ssh -L 8000:localhost:8000 -L 6333:localhost:6333 truviq_domain@192.168.0.143
```

Set `VLLM_EMBEDDING_MODEL` to the actual embedding model served by vLLM. Do not set it to a chat-only model.

After deployment, if the existing Qdrant collection was built with a different embedding dimension/model, use a clean collection or recreate it, then run:

```text
POST /api/ingest/reindex-embeddings
```

The backend automatically creates the new `search_states` SQL table on startup.

See `TRUHIRE_FIXES.md` and `backend/backend/README_UPDATED.md` for details.
