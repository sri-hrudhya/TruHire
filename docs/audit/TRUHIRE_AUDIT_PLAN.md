# TruHire Full Repository Cleanup and Audit Plan

## 1. Objective

Perform a repository-wide, evidence-based audit of TruHire covering source-code reachability, dependencies, security, AI governance, production readiness, and scalability.

The objective is to identify genuine defects, unused code, duplicated logic, security weaknesses, AI governance gaps, and operational bottlenecks without breaking existing functionality or deleting code based on incomplete evidence.

The audit must establish the current repository baseline, map static and runtime dependencies, validate findings through tests and configuration review, and produce a documented set of recommended changes.

**No source-code modifications, file deletions, dependency upgrades, or cleanup operations are permitted during the initial audit.** Implementation may begin only after the findings and proposed changes have been presented and explicitly approved.

## 2. Repository Context

The current repository is understood to contain:

- A FastAPI/Python backend under `backend/`, with approximately 66 Python files.
- A React/Vite frontend under `frontend/src/`, with approximately 77 source files.
- PostgreSQL, Redis, Qdrant, OpenSearch, and OpenAI-compatible inference integrations configured through environment settings.
- Laya decision-model integration in `backend/services/llm/laya_service.py`.
- Deterministic category classification in `backend/services/classification.py`.
- Output guardrails in `backend/services/llm/guardrails.py`.
- Prompt-injection screening, PII handling, and an AI audit trail.
- Backend and frontend tests, browser tests, application configuration, Docker services, operational scripts, sample data, and documentation.

These counts and descriptions are preliminary and must be verified against the actual repository.

The repository may also contain tracked archives, resume/JD samples, generated files, virtual environments, caches, build output, logs, uploaded documents, and dependency installations.

Treat all of these as separate repository or runtime surfaces. Do not assume that a tracked file is disposable or that an ignored file is irrelevant.

## 3. Mandatory Safety and Execution Rules

1. Preserve the existing working tree, user modifications, and repository history.
2. Do not delete, overwrite, rename, or refactor files during the initial audit.
3. Do not modify `.env` files or expose credentials, tokens, private keys, or connection strings.
4. Do not copy personal resume/JD data, secrets, or sensitive logs into reports.
5. Do not upload private repository contents to external services or AI providers without explicit authorization.
6. Do not remove code solely because it lacks a direct text-search match, import reference, or test coverage.
7. Account for dynamic imports, dependency injection, decorators, plugin registration, environment flags, optional providers, scripts, tests, and deployment configuration.
8. Distinguish existing failures from failures introduced by any later approved changes.
9. Use synthetic or explicitly approved non-sensitive data for testing.
10. Do not run destructive database operations or load tests against production without explicit authorization and a controlled test plan.
11. Separate confirmed findings from hypotheses, assumptions, and recommendations.
12. Preserve existing behavior unless a behavior change has been explicitly approved.
13. Present proposed deletions and other material changes for review before implementation.
14. Do not claim that a security control, test, integration, or runtime path works until there is evidence supporting that conclusion.

## 4. Phase 1 — Establish the Repository Baseline

### 4.1 Capture repository state

Record:

- Git branch and commit hash.
- Working-tree status and existing modifications.
- Tracked file inventory.
- Ignored and generated directories.
- Source files, tests, configurations, scripts, documentation, archives, and runtime assets.
- Existing untracked files and local artifacts relevant to the audit.

Use read-only Git operations wherever possible. Do not discard or clean existing user changes.

### 4.2 Identify application entry points

Inventory:

- FastAPI application initialization.
- Backend startup and shutdown hooks.
- API routers and dependency registration.
- Worker entry points and background tasks.
- CLI tools and maintenance scripts.
- Frontend startup and routing.
- Dockerfiles and Docker Compose services.
- CI workflows and deployment scripts.
- Database migrations and initialization.
- Test discovery and test configuration.

### 4.3 Establish the test baseline

Run the existing checks where the environment permits:

- Backend unit and integration tests.
- Frontend unit and component tests.
- Frontend production build.
- Browser/end-to-end tests.
- Available lint and type checks.
- Dependency and configuration validation.
- Docker Compose configuration validation.
- Relevant startup and health checks.

Record commands, exit codes, skipped tests, environment limitations, and existing failures.

Do not make source changes merely to make the baseline pass.

### Phase 1 exit criteria

A reproducible repository inventory exists, entry points are documented, and existing test and runtime health are recorded.

## 5. Phase 2 — Build Backend and Frontend Reachability Graphs

### 5.1 Backend dependency and execution graph

Build a graph covering:

- Module imports.
- Function and class references.
- Important call relationships.
- FastAPI router registration.
- Middleware and dependency injection.
- Startup and shutdown hooks.
- Background tasks and workers.
- Provider and plugin registration.
- Database models and persistence services.
- Configuration and environment-dependent branches.
- Scripts, migrations, tests, and deployment references.

Classify backend modules as:

1. Application-reachable.
2. Test-only.
3. Operational or maintenance tooling.
4. Optional-provider implementation.
5. Compatibility or migration code.
6. Dynamically referenced.
7. Potentially orphaned.
8. Unresolved due to insufficient evidence.

Use AST-based analysis and other appropriate static-analysis tools where practical. Do not treat a static graph as complete proof of runtime behavior.

### 5.2 Frontend dependency and execution graph

Build a graph covering:

- JavaScript/TypeScript imports and exports.
- Application entry points.
- Routes and lazy-loaded routes.
- Components and their consumers.
- Hooks, context providers, and state management.
- API clients and backend endpoints.
- CSS, Tailwind classes, and stylesheet imports.
- Images, fonts, icons, and other assets.
- Vite configuration and build-time references.
- Test utilities, mocks, and browser tests.
- Environment-dependent features.

Identify:

- Unreachable routes.
- Potentially unused components.
- Dead exports.
- Duplicate utilities.
- Unused styles and assets.
- Files referenced only by tests or tooling.

Do not recommend removing dynamically loaded modules or assets without validating their consumers.

### Phase 2 exit criteria

Both dependency graphs are documented, and uncertain references are explicitly identified rather than silently classified as unused.

## 6. Phase 3 — Unused Code, Duplication, and Dependency Audit

### 6.1 Code-quality review

Inspect for:

- Unused imports and variables.
- Unreachable branches.
- Dead exports.
- Duplicate logic.
- Stale compatibility code.
- Obsolete comments and documentation.
- Debug statements and temporary development remnants.
- Inconsistent error handling.
- Unnecessary complexity.
- Unhandled exceptions.
- Missing input validation.
- Inconsistent configuration defaults.

Use linting, static analysis, coverage, type checking, and targeted tests where available.

Coverage absence is a signal for investigation, not proof that code is unnecessary.

### 6.2 Dependency audit

Inspect backend and frontend dependency manifests and lockfiles.

Identify:

- Direct and transitive dependencies.
- Potentially unused packages.
- Duplicate functionality.
- Version drift.
- Inconsistent or stale lockfiles.
- Optional dependencies and provider-specific packages.
- Known vulnerabilities using approved local or authorized advisory sources.
- Unpinned or irreproducible dependencies.
- Unnecessary packages in production images.
- Development dependencies accidentally included in runtime images.

Do not upgrade or uninstall dependencies during the audit.

Any proposed dependency removal must account for dynamic imports, plugin discovery, CLI entry points, packaging requirements, and deployment behavior.

### 6.3 Candidate-deletion evidence standard

Every proposed deletion must have an evidence record containing:

- File path or exact code range.
- Description of the candidate.
- Why it appears unused or redundant.
- Static-analysis evidence.
- Import, call, route, configuration, and runtime-reference checks.
- Test and build implications.
- Potential behavior or compatibility risks.
- Confidence level: High, Medium, or Low.
- Recommended action.

Require multiple independent signals before recommending removal.

High-confidence candidates may be proposed for approval. Medium-confidence candidates require further investigation. Low-confidence candidates should be retained until their purpose is established.

### Phase 3 exit criteria

Potential cleanup candidates are documented with evidence. No code or dependency changes have been applied.

## 7. Phase 4 — Security Audit

Conduct a defensive review of the application's actual implementation and configuration.

### 7.1 Authentication and authorization

Inspect:

- Authentication flows.
- JWT/session handling, where implemented.
- Token expiration and validation.
- Password and credential handling.
- Role and permission checks.
- Resource ownership checks.
- Administrative endpoint protection.
- Authentication bypass possibilities.
- Authorization enforcement across backend routes.

Verify that security-sensitive operations enforce authorization on the server rather than relying solely on frontend controls.

### 7.2 API and application security

Inspect:

- Input validation and serialization.
- SQL injection and unsafe query construction.
- Path traversal.
- SSRF.
- Unsafe file upload and download behavior.
- MIME type and file-size validation.
- CORS configuration.
- Rate limits and abuse controls.
- Error and exception exposure.
- Security-sensitive logging.
- Request-size and resource-exhaustion risks.
- Email delivery and abuse controls.
- Insecure defaults and debug settings.

Only test against authorized local or staging environments using controlled inputs.

### 7.3 Secrets and infrastructure

Inspect:

- Secret exposure in source, configuration, images, and logs.
- `.env` handling and secret-loading practices.
- Dockerfile and container privileges.
- Network exposure and service binding.
- TLS termination assumptions.
- Persistent storage and permissions.
- Health checks and restart policies.
- Dependency vulnerability exposure.
- Database access boundaries.
- Redis, Qdrant, and OpenSearch authentication and network restrictions.
- Inference-provider credentials and outbound connections.

Never print actual secrets into audit findings.

### 7.4 Data protection

Inspect:

- PII collection and processing.
- Resume and job-description storage.
- Access controls for uploaded documents.
- PII redaction before logging or external inference.
- Data retention and deletion behavior.
- Temporary files and generated artifacts.
- Audit-log access and retention.
- Backups containing sensitive information.
- Data transmission to external providers.

Document actual behavior and configuration. Do not claim regulatory compliance without sufficient evidence.

### 7.5 Security finding format

Every finding must include:

- Identifier.
- Severity: Critical, High, Medium, Low, or Informational.
- Confidence.
- Affected file and line range, where available.
- Evidence and reproduction conditions.
- Required attacker privileges or preconditions.
- Potential impact.
- Recommended remediation.
- Regression-test recommendation.
- Verification status.

Distinguish confirmed vulnerabilities from potential weaknesses that need further validation.

### Phase 4 exit criteria

Security findings are prioritized, evidence-backed, and accompanied by remediation recommendations.

## 8. Phase 5 — L1 Guardrails, Laya, and AI Governance Audit

### 8.1 Establish what L1 Guardrails means

Search the repository, documentation, configuration, and tests for the term "L1 Guardrails."

Determine whether it represents:

- An explicitly implemented layer.
- A project-specific architectural label.
- A documented concept without a corresponding implementation.
- A collection of controls distributed across several modules.

Map the actual controls to the terminology used by the project.

Do not invent a standard implementation or assume a module belongs to L1 simply because its name suggests it.

### 8.2 Trace AI execution paths

Trace AI-generated outputs from input to final response:

1. User or document input.
2. Input validation and normalization.
3. Prompt construction.
4. Model/provider selection.
5. Laya or other model execution.
6. Output parsing and schema validation.
7. Guardrail evaluation.
8. Fallback, blocking, retry, or escalation behavior.
9. Audit logging.
10. Final user-facing response.

Identify any path that bypasses validation or produces a result without the required security checks.

### 8.3 Laya integration

Audit `backend/services/llm/laya_service.py` and its callers.

Verify:

- Model initialization and lifecycle.
- Lazy loading or eager loading.
- Model configuration and version.
- Input and output contracts.
- Typed question conversion, if implemented.
- Timeout and exception behavior.
- Model-unavailable behavior.
- Fallback and failure policy.
- Confidence handling and escalation rules, if implemented.
- Caching and cache invalidation.
- Concurrency and resource usage.
- Audit trace propagation.
- Model output validation.
- Integration tests and available runtime evidence.

Do not assume that a numerical score, category, or structured response makes a model decision deterministic.

### 8.4 Deterministic classification

Audit `backend/services/classification.py`.

Document the actual implementation of:

- Supported categories.
- Keyword or feature rules.
- Category weights.
- Title multipliers.
- Score thresholds.
- Tie-breaking priority.
- Fallback or `Others` behavior.
- Input normalization.
- Handling of missing or ambiguous information.
- Downstream consumers of the classification.

Verify these details from code and tests rather than inferring them from documentation.

Where classification is rule-based, test that identical normalized inputs and configuration produce identical outputs.

### 8.5 Guardrails and prompt-injection defenses

Audit `backend/services/llm/guardrails.py` and related components.

Verify:

- Input and output validation.
- Prompt-injection screening.
- Treatment of untrusted resumes and job descriptions.
- Schema and type validation.
- Sensitive-data handling.
- Blocking and fallback decisions.
- Failure-open versus failure-closed behavior.
- Logging of guardrail verdicts.
- Tests for adversarial and malformed inputs.
- Potential bypasses between model execution and response delivery.

Use deterministic controls for explicit rules where appropriate. Treat AI-assisted screening as an additional control, not a guaranteed security boundary.

### 8.6 PII and AI audit trail

Verify:

- Which fields are classified as sensitive.
- Where redaction occurs.
- Whether PII reaches external providers.
- What prompt and output information is logged.
- Whether audit records contain sensitive content.
- How model versions, decisions, guardrail verdicts, and failures are correlated.
- Access control and retention for audit records.
- Whether the evidence is sufficient to reconstruct a decision without unnecessarily storing sensitive information.

### 8.7 AI decision governance

Assess whether TruHire clearly separates:

- Deterministic mandatory eligibility rules.
- Model-based semantic matching.
- Model-generated ranking or recommendations.
- Deterministic output validation.
- Human review and oversight.

Verify whether a model can override mandatory eligibility requirements.

Document how recruiters can understand why candidates were ranked, filtered, or classified. Avoid unsupported claims that the system is unbiased or fair; report the actual evaluations performed and their limitations.

### Phase 5 exit criteria

The report contains a verified AI execution map, actual L1 Guardrails interpretation, Laya behavior, deterministic classification rules, PII handling, and unresolved governance gaps.

## 9. Phase 6 — Production Readiness Audit

Evaluate the repository against the stated deployment baseline: Docker Compose used as a production deployment, with ongoing ingestion and concurrent users.

Do not assume that the presence of Docker Compose establishes production readiness.

Assess:

1. Deployment and configuration hygiene.
2. Secret management.
3. Authentication and authorization.
4. API security and abuse controls.
5. Application reliability.
6. Database connection management.
7. Persistent storage and backup strategy.
8. Backup restoration and disaster recovery.
9. Health checks and service restart behavior.
10. Logging, metrics, tracing, and alerting.
11. Resource limits and capacity management.
12. Database and index migrations.
13. Dependency and image reproducibility.
14. Data governance and retention.
15. Operational runbooks.
16. Test coverage and release gates.
17. Rollback and recovery procedures.
18. External-provider failure handling.

For each area, record:

- Status: Pass, Partial, Fail, or Not Verified.
- Evidence.
- Known gaps.
- Operational impact.
- Recommended remediation.
- Verification method.

Produce an overall readiness scorecard without presenting an arbitrary numerical score as proof of production readiness.

Explicitly distinguish:

- Verified in a controlled environment.
- Supported by static evidence.
- Inferred from configuration or architecture.
- Not tested.
- Dependent on infrastructure assumptions.

## 10. Phase 7 — Scalability Assessment for 1,000+ Resumes

Evaluate the ingestion, indexing, search, and concurrent-user architecture.

### 10.1 Ingestion and processing

Inspect:

- Resume upload handling.
- File parsing and extraction.
- Supported formats and file-size limits.
- CPU and memory consumption.
- Temporary-file usage.
- Background-task and queue behavior.
- Database write throughput.
- Embedding generation and inference latency.
- Retry and timeout behavior.
- Idempotency and duplicate prevention.
- Partial failures and recovery.

Determine whether FastAPI background tasks or an optional ARQ worker path is used in each configuration.

### 10.2 Storage and retrieval

Evaluate:

- PostgreSQL table growth and query patterns.
- Database connection-pool pressure.
- Redis usage, memory requirements, and cache behavior.
- Qdrant collection configuration, vector dimensions, indexing, and query behavior.
- OpenSearch mappings, shard configuration, indexing throughput, and query performance.
- Disk consumption per resume.
- Embedding and index storage overhead.
- Consistency between PostgreSQL records and search indexes.

### 10.3 Inference and external dependencies

Evaluate:

- LLM/provider rate limits.
- Embedding throughput.
- Laya inference latency and resource requirements.
- Timeouts, retries, and backpressure.
- Concurrent model requests.
- Provider failure behavior.
- Cost and resource assumptions where relevant.

Do not assume an OpenAI-compatible endpoint has the same capacity, behavior, or guarantees as another provider.

### 10.4 Concurrent access

Assess:

- Concurrent API requests.
- Upload concurrency.
- Search concurrency.
- Database pool saturation.
- Redis contention.
- Vector and lexical search latency.
- LLM request contention.
- Queue growth.
- Resource exhaustion.
- Error rates under load.

Identify architectural bottlenecks from code and configuration, then validate them through controlled measurements.

### Phase 7 exit criteria

Produce a bottleneck report separating static observations from measured results. Do not claim support for 1,000+ resumes without representative benchmark evidence and documented infrastructure assumptions.

## 11. Phase 8 — Bounded Load-Test Plan

Prepare and execute the load test only after the environment and safety boundaries have been approved.

### 11.1 Test environment

Use:

- A dedicated local or authorized staging environment.
- Synthetic or approved non-sensitive resumes and job descriptions.
- Representative file sizes and supported formats.
- Controlled provider stubs or explicitly approved staging inference services.
- Isolated test databases and indexes.
- Documented CPU, RAM, disk, and network resources.

Do not run uncontrolled load tests against production or unapproved external providers.

### 11.2 Benchmark scenarios

Establish a baseline and evaluate staged workloads:

| Scenario | Objective |
|---|---|
| 100 resumes | Establish baseline throughput and resource consumption. |
| 1,000 resumes | Measure batch ingestion and indexing behavior. |
| 5,000 resumes | Assess larger-scale resource growth and queue pressure. |
| Concurrent API requests | Measure throughput, latency, and errors. |
| Concurrent search requests | Measure retrieval performance and index health. |
| Concurrent ingestion and search | Evaluate contention between workloads. |
| Inference-provider outage | Validate timeouts, fallback, and recovery. |
| Worker restart during processing | Validate recovery, retries, and duplicate prevention. |
| Database or search-service interruption | Assess failure propagation and recovery where safe. |

These are proposed test scenarios, not guaranteed capacity targets.

### 11.3 Metrics

Capture:

- Upload acceptance rate.
- Resume extraction throughput.
- Indexing throughput.
- Queue depth and queue completion time.
- Total batch completion time.
- Error and duplicate rates.
- Retry counts and failed jobs.
- CPU, RAM, and disk consumption.
- Database connection utilization.
- PostgreSQL query latency.
- Qdrant and OpenSearch indexing and search latency.
- API throughput.
- p50, p95, and p99 latency.
- Timeout and error rates.
- Recovery time after controlled failures.

### 11.4 Pass/fail criteria

Before testing, define acceptable limits for:

- Batch completion time.
- API and search latency.
- Error and timeout rates.
- Maximum resource utilization.
- Queue growth and recovery.
- Duplicate processing.
- Service recovery after failure.

Choose limits based on the intended workload and infrastructure rather than inventing universal thresholds.

### 11.5 Reporting

For every benchmark, record:

- Environment and resource allocation.
- Application and dependency versions.
- Dataset size and characteristics.
- Concurrency and request-rate settings.
- Test duration.
- Warm-up and cache conditions.
- Measured results.
- Errors and limitations.
- Whether the result is reproducible.

Do not equate ingestion capacity with simultaneous-user capacity.

## 12. Phase 9 — Produce the Audit Reports

### Deliverable A: Repository Audit Report

Include:

- Repository inventory.
- Architecture and dependency graphs.
- Entry points and runtime surfaces.
- Reachability classifications.
- Unused-code and duplication candidates.
- Dependency/build health.
- Baseline test results.
- Evidence-backed cleanup recommendations.

### Deliverable B: Security and AI Governance Report

Include:

- Authentication and authorization findings.
- Vulnerability severity and reproduction evidence.
- Configuration and infrastructure risks.
- PII and data-retention findings.
- L1 Guardrails interpretation.
- Laya execution and failure behavior.
- Deterministic classification rules.
- Prompt-injection defenses.
- AI output validation and auditability.
- Human oversight and unresolved governance risks.

### Deliverable C: Production Readiness and Scalability Report

Include:

- Production-readiness scorecard.
- Deployment and operational gaps.
- Static bottleneck analysis.
- Benchmark design and results.
- Resource measurements.
- Capacity conclusions supported by evidence.
- Infrastructure assumptions and residual risks.
- Prioritized recommendations.

### Deliverable D: Proposed Cleanup Change Set

Include a precise list of proposed changes, organized by priority.

For each proposed deletion or modification, provide:

- File and code range.
- Reason.
- Supporting evidence.
- Reference and runtime checks performed.
- Test implications.
- Risk and confidence.
- Expected behavior impact.
- Proposed regression tests.

Also provide a separate list of items that require human or product confirmation, including ambiguous archives, sample resumes/JDs, compatibility modules, and uncertain runtime references.

### Deliverable E: Validation Matrix

Track:

- Existing baseline.
- Proposed change.
- Relevant tests.
- Test result before cleanup.
- Test result after approved cleanup.
- Runtime verification.
- Remaining failures.
- Outstanding uncertainty.

## 13. Phase 10 — Review and Approval Gate

Before modifying the repository, present:

1. Executive summary of findings.
2. Prioritized security and reliability issues.
3. Confirmed and potential unused-code candidates.
4. Proposed dependency changes.
5. AI governance gaps.
6. Production-readiness findings.
7. Scalability findings and test limitations.
8. Exact proposed file deletions and modifications.
9. Expected benefits and potential regressions.
10. Required human or product decisions.

Wait for explicit approval before implementing cleanup changes.

Security findings may be reported immediately, but do not silently alter authentication, authorization, AI decisions, data retention, or other behavior during the audit.

## 14. Phase 11 — Apply Approved Changes and Verify

After approval:

1. Apply only approved changes.
2. Preserve unrelated working-tree modifications.
3. Make small, logically grouped changes.
4. Add narrowly scoped regression tests for verified defects.
5. Run focused tests after each change group.
6. Run the relevant full backend and frontend test suites.
7. Rebuild the frontend.
8. Validate Docker Compose and relevant startup paths.
9. Recheck import, route, provider, and runtime registration.
10. Run approved security regression tests.
11. Compare results against the original baseline.
12. Update the audit reports to reflect actual outcomes.
13. Document unresolved issues and limitations.

Do not claim that the cleanup is successful if required tests fail without explanation.

If a change introduces a regression, investigate and correct or revert the approved change rather than masking the failure.

## 15. Final Acceptance Criteria

The audit is complete when:

- The repository inventory is documented.
- Backend and frontend reachability graphs are available.
- Potentially unused code has evidence-backed classifications.
- Dependencies and build health have been reviewed.
- Security findings are prioritized and documented.
- L1 Guardrails and Laya behavior have been traced through actual execution paths.
- Deterministic classification rules have been verified.
- AI governance and PII handling have been assessed.
- Production readiness is evaluated against documented criteria.
- Scalability conclusions distinguish static analysis from measurements.
- The bounded load-test plan and its results are documented where executed.
- All proposed removals have supporting evidence and approval status.
- Approved changes have been tested against the original baseline.
- Residual risks and unresolved questions are explicitly reported.

## 16. Final Operating Principle

**Inventory → Map → Audit → Validate → Report → Obtain Approval → Implement → Regression-Test.**

Preserve behavior by default. Require multiple independent signals before recommending deletion. Treat missing evidence as uncertainty rather than proof of absence.

Do not delete source code, archives, samples, or runtime data merely to reduce repository size.

Do not claim production readiness or a particular capacity based on static analysis or unit tests alone.

The final outcome must be an auditable, evidence-backed understanding of TruHire, a prioritized set of recommended improvements, and a verified cleanup change set containing only approved changes.