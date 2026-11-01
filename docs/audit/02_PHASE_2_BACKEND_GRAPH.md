# Phase 2 — Backend Dependency and Reachability Audit

## Goal
Map backend modules and execution paths, then classify files without prematurely declaring anything unused.

## Scope
Primarily `backend/`, plus relevant tests, configuration, scripts, migrations, Docker/CI files, and deployment references.

## Tasks
1. Reuse the Phase 1 inventory and baseline; do not repeat broad inventory unless a gap is found.
2. Identify application entry points, FastAPI router registration, middleware, dependencies, startup/shutdown hooks, background tasks, ARQ workers if configured, CLI scripts, scheduled jobs, migrations, and maintenance tools.
3. Build an import graph and, where practical, call/reference relationships using AST or existing tooling.
4. Trace dynamic imports, decorators, dependency injection, provider/plugin registries, environment-gated code, optional providers, reflection, and string-based module references.
5. Map API routes to handlers, service layers, persistence, external services, and response paths.
6. Map tests to the modules and behaviors they exercise.
7. Classify modules as application-reachable, test-only, operational, optional-provider, compatibility/migration, dynamically referenced, potentially orphaned, or unresolved.
8. For suspicious modules, inspect targeted surrounding code and configuration. Do not read every file in full without a reason.
9. Do not remove or edit code.

## Required report
Save to `docs/audit/02_PHASE_2_BACKEND.md`:
- Backend architecture and entry points.
- Graph generation method and limitations.
- Router/service/worker/provider relationships.
- Potentially orphaned modules with evidence and confidence.
- Dynamic/runtime references requiring validation.
- Targeted tests or checks performed.
- Unresolved questions.

## Exit criteria
A backend reachability map and evidence-backed candidate list exist. No application source changes. Wait for approval before Phase 3.
