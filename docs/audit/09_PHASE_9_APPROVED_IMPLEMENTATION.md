# Phase 9 — Implement Approved Changes Only

## Preconditions
The user has explicitly approved the exact changes or a clearly bounded batch listed in `docs/audit/PROPOSED_CHANGES.md`. If approval is ambiguous, ask before proceeding.

## Rules
1. Recheck Git status and preserve all unrelated user modifications.
2. Apply only approved changes. Do not opportunistically refactor adjacent code.
3. Work in small, logically grouped batches.
4. For each removal, recheck dynamic imports, router/worker/provider registration, configuration, scripts, Docker/CI, tests, and external entry points.
5. Add narrowly scoped regression tests for verified defects where appropriate.
6. Do not alter authentication, authorization, data retention, AI decisions, or security behavior beyond the approved scope.
7. Do not expose secrets or sensitive resume/JD data.
8. Never delete archives, samples, uploads, logs, or runtime data unless specifically approved.
9. Update manifests/lockfiles only when the approved change requires it.
10. If a change reveals uncertainty or a new behavior impact, stop that change and report the issue rather than expanding scope.

## Validation after each batch
Run relevant:
- Focused unit/integration tests.
- Backend lint/type checks.
- Frontend unit/component tests.
- Frontend production build.
- Browser/E2E tests where relevant.
- Docker Compose configuration/startup checks where safe.
- Security regression tests for security fixes.
- Targeted runtime checks.

Compare against the original baseline. Clearly report pre-existing failures, new failures, skipped tests, and environment limitations.

## Rollback rule
If an approved change introduces a regression, investigate and correct or revert that change. Do not mask or silently accept failures.

## Required outputs
Update:
- `docs/audit/VALIDATION_MATRIX.md`
- `docs/audit/FINAL_AUDIT_REPORT.md`
- `docs/audit/PROPOSED_CHANGES.md` with completed/deferred status

Report exact changed files, rationale, tests, before/after results, remaining risks, and any deviations from the approved scope.

## Exit criteria
Only approved changes are present, relevant validation has run, and the resulting evidence is documented. Do not claim success where required tests remain failing or unverified.
