# Phase 1 — Repository Baseline and Inventory

## Goal
Establish a reproducible picture of the repository and current health. This phase is read-only.

## Instructions for the coding agent
1. Read `docs/audit/00_MASTER_PLAN.md` if present; otherwise use the master plan supplied by the user.
2. Run `git status --short --branch` and record the current commit. Do not discard, stash, reset, or overwrite user changes.
3. Inventory tracked files and classify them: backend, frontend, tests, configuration, scripts, docs, migrations, Docker/deployment, archives, samples/fixtures, and other assets.
4. Identify ignored/generated directories without recursively dumping their contents. Examples may include virtual environments, caches, `node_modules`, build output, logs, uploads, and generated files.
5. Identify backend/frontend entry points, FastAPI app initialization, router registration, middleware, startup/shutdown hooks, workers/background tasks, frontend routes, Vite configuration, Docker Compose services, CI workflows, and test discovery.
6. Identify available test, lint, type-check, build, and Compose validation commands from repository configuration. Run safe checks where practical.
7. Record pre-existing failures, skipped checks, missing dependencies, and environment limitations.
8. Note tracked archives and sample resumes/JDs for review; do not delete or reproduce sensitive content.
9. Save findings to `docs/audit/01_PHASE_1_BASELINE.md`. Create only the audit report directory/files if necessary; do not change application code.
10. Stop after Phase 1 and summarize findings concisely.

## Safety
- Do not print secrets or personal data.
- Do not run destructive database commands or load tests.
- Do not modify source code, manifests, lockfiles, or runtime data.

## Required report
- Commit and working-tree status.
- Inventory counts and classification method.
- Entry points and runtime surfaces.
- Available validation commands and results.
- Existing failures and limitations.
- Ambiguities requiring later investigation.
- Confirmation that no application files were changed.

## Exit criteria
A reproducible baseline exists and the current state is preserved. Wait for explicit approval before Phase 2.
