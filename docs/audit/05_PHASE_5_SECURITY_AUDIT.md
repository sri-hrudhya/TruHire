# Phase 5 — Security Audit

## Goal
Review application security using static inspection, safe configuration checks, and authorized tests. Do not exploit production systems or make fixes during this audit phase.

## Scope
Backend routes/services, frontend auth flows, configuration, Docker/Compose, dependencies, storage, upload/download paths, inference integrations, logging, and deployment scripts.

## Areas to inspect
### Authentication and authorization
- Authentication flows and token/session validation.
- Expiration, signature/issuer/audience checks where applicable.
- Role and permission boundaries.
- Resource ownership checks.
- Admin routes and server-side enforcement.
- Password/credential handling.

### API and application
- Input validation and serialization.
- SQL/query construction.
- Path traversal and unsafe file handling.
- SSRF and outbound request controls.
- Upload size/type/content validation.
- CORS, rate limits, request limits, and abuse controls.
- Error leakage and sensitive logging.
- Email delivery abuse and resource exhaustion.

### Secrets and infrastructure
- Secret exposure in source, images, logs, and config.
- `.env` loading and handling (never print values).
- Container privileges, exposed ports, network boundaries, health checks, restart policies, TLS assumptions, persistent storage, and service credentials.
- PostgreSQL, Redis, Qdrant, OpenSearch, and inference endpoint access controls.
- Dependency/image vulnerability status using approved sources.

### Privacy and data protection
- Resume/JD PII handling, access control, retention/deletion, temporary files, logs, backups, and external provider transmission.
- Whether redaction occurs before logging or model calls where required.

## Testing boundaries
- Use local or authorized staging only.
- Use synthetic or approved non-sensitive fixtures.
- No destructive database operations, production probing, uncontrolled load, or external data transmission without authorization.
- Do not expose secrets or personal data in reports.

## Finding format
For each finding: ID, severity (Critical/High/Medium/Low/Informational), confidence, file/line, evidence, preconditions, impact, remediation, regression test, and verification status. Distinguish confirmed vulnerabilities from hypotheses.

## Required report
Save to `docs/audit/05_PHASE_5_SECURITY.md`. Include confirmed findings, potential issues, tests performed, limitations, and prioritized remediations. Do not modify code.

## Exit criteria
Security findings are evidence-backed and prioritized. Wait for approval before remediation.
