# Phase 7 — Production Readiness and Scalability Assessment

## Goal
Assess readiness against the stated baseline: Docker Compose used as a production deployment, continuous ingestion, and concurrent users. Separate static evidence from measured behavior.

## A. Production readiness
Assess:
- Deployment/configuration hygiene and secret management.
- Authentication, authorization, API security, and abuse controls.
- Reliability, timeouts, retries, idempotency, and graceful degradation.
- PostgreSQL connection pooling, migrations, backup/restore, and recovery.
- Redis configuration and persistence expectations.
- Qdrant/OpenSearch security, indexing, persistence, and recovery.
- Health checks, restart policies, resource limits, and network exposure.
- Logging, metrics, tracing, alerting, and operational runbooks.
- Dependency/image reproducibility and release/rollback gates.
- PII retention and data governance.
- Test confidence and environment parity.

For each item record Pass/Partial/Fail/Not Verified, evidence, gap, impact, remediation, and verification method. Do not use an arbitrary overall score as proof of readiness.

## B. Scalability analysis for 1,000+ resumes
Inspect:
- Upload limits and extraction/parser throughput.
- CPU, RAM, temporary disk, and storage per resume.
- Background task/ARQ queue configuration and worker concurrency.
- Retry, timeout, idempotency, duplicate handling, and partial failures.
- PostgreSQL query patterns, pool pressure, and write throughput.
- Redis memory/cache behavior.
- Qdrant vector dimensions, collection/index configuration, ingestion and query behavior.
- OpenSearch mappings, shards, indexing throughput, and query latency.
- Embedding/model throughput, provider rate limits, Laya latency, and failure behavior.
- Concurrent API/search/ingestion contention.

Do not assume both FastAPI background tasks and ARQ are active. Verify each configured path.

## C. Benchmark plan
Prepare a controlled plan using synthetic/approved non-sensitive fixtures and a local or authorized staging environment. Proposed scenarios:
- 100 resumes for baseline.
- 1,000 resumes for batch ingestion.
- 5,000 resumes for larger-scale resource growth.
- Concurrent API and search requests.
- Concurrent ingestion and search.
- Provider outage/fallback.
- Worker restart/retry/idempotency.
- Safe dependency interruption/recovery tests where feasible.

These are test sizes, not capacity claims. Define workload and pass/fail thresholds before execution.

Measure:
- Upload acceptance and extraction/indexing throughput.
- Queue depth and completion time.
- Error, timeout, retry, and duplicate rates.
- CPU/RAM/disk.
- DB connections/query latency.
- Qdrant/OpenSearch indexing/search latency and index health.
- API throughput and p50/p95/p99 latency.
- Recovery time and backlog drainage.

Record hardware, versions, dataset, file sizes, concurrency, request rate, duration, warm-up/cache conditions, errors, and limitations.

## Safety
Do not run uncontrolled load or destructive tests against production. Do not send sensitive data to external providers without authorization.

## Required report
Save to `docs/audit/07_PHASE_7_READINESS_SCALABILITY.md`. Clearly label each conclusion as static, inferred, measured, or not verified. Include infrastructure assumptions and unresolved bottlenecks. Do not modify code.

## Exit criteria
A readiness scorecard, bottleneck assessment, and bounded benchmark plan exist. Any capacity claim must be backed by representative measurements.
