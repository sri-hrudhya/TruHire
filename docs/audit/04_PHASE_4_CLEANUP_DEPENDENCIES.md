# Phase 4 — Unused Code, Duplication, and Dependency Audit

## Goal
Consolidate backend/frontend graph findings to identify defensible cleanup candidates. This phase remains read-only.

## Tasks
1. Read Phases 1–3 reports and investigate only relevant gaps.
2. Use existing linters/static-analysis tools to find unused imports, variables, exports, unreachable branches, duplicate helpers, stale compatibility code, debug remnants, and inconsistent error handling.
3. Treat missing test coverage as a signal for investigation, not proof of unused code.
4. Review backend/frontend manifests and lockfiles for direct/transitive dependencies, duplicate functionality, version drift, optional dependencies, reproducibility issues, and known vulnerabilities using approved sources.
5. Check packaging, dynamic imports, plugin/provider registration, CLI tools, scripts, tests, build configuration, and Docker/runtime use before proposing dependency removal.
6. Do not upgrade, uninstall, or change dependencies.
7. Do not remove or edit code.

## Candidate evidence requirements
For each candidate, record:
- Exact path and line range or package name.
- Proposed action and rationale.
- Static-analysis evidence.
- Import/call/router/config/runtime checks.
- Tests/build checks relevant to the candidate.
- Risk and possible behavior/compatibility impact.
- Confidence: High, Medium, or Low.
- Recommended next validation.

Use multiple independent signals. Keep medium/low-confidence items pending investigation.

## Required report
Save to `docs/audit/04_PHASE_4_CLEANUP_CANDIDATES.md`:
- Candidate cleanup table.
- Dependency findings.
- Duplication and maintainability findings.
- Validation evidence and limitations.
- Separate list of items requiring product/human confirmation.
- No changes made.

## Exit criteria
A reviewable, evidence-backed list exists. Wait for explicit approval before any cleanup implementation.
