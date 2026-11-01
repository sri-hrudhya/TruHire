# TruHire Full Cleanup and Audit — Master Plan

## Objective
Perform an evidence-based audit of TruHire covering repository inventory, backend/frontend reachability, unused code, dependencies, security, AI governance, production readiness, and scalability. Preserve behavior by default and make no cleanup changes until findings have been reviewed and explicitly approved.

## Known repository context (verify against actual repository)
- FastAPI/Python backend under `backend/`.
- React/Vite frontend under `frontend/src/`.
- PostgreSQL, Redis, Qdrant, OpenSearch, and OpenAI-compatible inference integrations.
- Laya integration in `backend/services/llm/laya_service.py`.
- Deterministic category classification in `backend/services/classification.py`.
- Output guardrails in `backend/services/llm/guardrails.py`.
- Prompt-injection screening, PII handling, and AI audit trail.
- Docker Compose, tests, browser tests, scripts, docs, archives, and sample data.

These details are preliminary and must be verified.

## Non-negotiable rules
1. Inspect Git status before any work; preserve all existing user changes.
2. Initial audit is read-only: do not edit application source, delete files, upgrade dependencies, or clean generated/runtime data.
3. Never expose `.env` contents, credentials, tokens, private keys, or sensitive resume/JD contents in chat or reports.
4. Do not send private repository data to external services without explicit authorization.
5. Do not classify code as unused solely because text search finds no references or tests do not cover it.
6. Check dynamic imports, dependency injection, decorators, plugin/provider registries, environment flags, routers, workers, scripts, tests, Docker, CI, and deployment references.
7. Separate confirmed facts, hypotheses, recommendations, and unverified assumptions.
8. Record commands and test results, including pre-existing failures and environment limitations.
9. Use synthetic or approved non-sensitive fixtures for tests.
10. Do not run destructive operations or uncontrolled load tests against production.
11. Report evidence and confidence for every proposed deletion.
12. Obtain explicit approval before applying cleanup or behavior-changing fixes.

## Phase order
1. Repository baseline and inventory.
2. Backend reachability and dependency map.
3. Frontend reachability and dependency map.
4. Unused code, duplication, and dependency audit.
5. Security audit.
6. L1 Guardrails, Laya, and AI governance audit.
7. Production readiness and scalability assessment.
8. Consolidated report and proposed change set.
9. After approval only: apply approved changes and regression-test.

## Evidence standard for proposed removals
Each candidate must include exact path/lines, reason, multiple independent signals, import/call/router/config/runtime checks, test/build implications, risks, confidence (High/Medium/Low), and recommendation. Uncertain candidates must be retained pending investigation.

## Final deliverables
- Repository audit report.
- Security and AI governance report.
- Production-readiness and scalability report.
- Evidence-backed cleanup candidate list.
- Explicit human/product decision list.
- After approval, a cleanup change set and before/after validation matrix.

## Operating principle
Inventory → Map → Audit → Validate → Report → Obtain Approval → Implement → Regression-Test.
