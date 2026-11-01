# Phase 3 — Frontend Dependency and Reachability Audit

## Goal
Map the frontend source, route, component, asset, style, and test relationships.

## Scope
`frontend/src/` plus package manifests, lockfiles, Vite configuration, TypeScript configuration, tests, browser-test configuration, build scripts, and runtime environment configuration.

## Tasks
1. Reuse prior inventory; do not repeat broad repository scans.
2. Identify app entry points, router setup, eager/lazy routes, dynamic imports, layouts, page components, hooks, providers, state management, and API clients.
3. Build import/export references and identify possible dead exports or disconnected components.
4. Check CSS imports, Tailwind usage/configuration, global styles, CSS modules, dynamically composed class names, fonts, icons, and assets.
5. Check Vite aliases, build-time environment variables, test mocks, test setup files, browser tests, and tooling-only references.
6. Map frontend API calls to known backend endpoints where practical; record mismatches for investigation rather than assuming they are defects.
7. Identify duplicated helpers and suspicious unused files, with confidence and evidence.
8. Do not remove files, rewrite components, or change dependencies.

## Required report
Save to `docs/audit/03_PHASE_3_FRONTEND.md`:
- Entry points and route map.
- Component/hook/API-client relationships.
- Style and asset reference findings.
- Build/test/tooling-only files.
- Potentially unreachable files and independent evidence.
- Dynamic-reference caveats and unresolved questions.
- Commands and checks run.

## Exit criteria
Frontend reachability and candidate findings are documented without source changes. Wait for approval before Phase 4.
