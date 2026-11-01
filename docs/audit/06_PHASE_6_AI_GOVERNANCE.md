# Phase 6 — L1 Guardrails, Laya, and AI Governance Audit

## Goal
Trace AI-related execution paths and verify what controls actually do. Do not infer behavior from filenames or documentation alone.

## A. Establish “L1 Guardrails”
Search source, tests, config, and documentation for the term. Determine whether it is a concrete implementation layer, project-specific label, distributed set of controls, or documentation-only term. Map actual controls to the label and call out terminology gaps.

## B. Trace AI execution paths
For each relevant workflow, trace:
1. User/document input.
2. Validation and normalization.
3. Prompt construction.
4. Model/provider selection.
5. Laya or other model execution.
6. Output parsing/schema validation.
7. Guardrail verdict.
8. Block/fallback/retry/escalation behavior.
9. Audit logging and trace propagation.
10. User-facing result.

Identify any path that bypasses validation or logs sensitive content.

## C. Laya integration
Inspect `backend/services/llm/laya_service.py` and callers for:
- Initialization/lifecycle and loading behavior.
- Model/version/configuration.
- Input/output contracts and typed question conversion, if present.
- Timeout, exception, unavailable-model, fallback, and failure behavior.
- Confidence/escalation logic, if implemented.
- Caching and invalidation.
- Concurrency/resource use.
- Audit trace propagation and output validation.
- Relevant tests and runtime evidence.

Do not assume scores or structured output make model decisions deterministic.

## D. Deterministic classification
Inspect `backend/services/classification.py`. Verify:
- Categories and normalization.
- Keyword/feature rules and weights.
- Title multipliers.
- Thresholds and tie priority.
- `Others` or fallback behavior.
- Missing/ambiguous input behavior.
- Downstream consumers.
- Tests showing repeatability for identical normalized inputs/configuration.

Document actual implementation; do not infer details.

## E. Guardrails and prompt injection
Inspect `backend/services/llm/guardrails.py` and related code for:
- Input/output validation.
- Treatment of untrusted resume/JD text.
- Prompt-injection screening and its limits.
- Schema/type validation.
- Blocking/fallback behavior.
- Failure-open vs failure-closed behavior.
- Guardrail logging and bypass paths.
- Tests for malformed/adversarial inputs.

Treat AI-assisted screening as an additional control, not a guaranteed security boundary.

## F. PII and audit trail
Verify:
- Sensitive fields and redaction points.
- Whether PII reaches external providers.
- Prompt/output logging behavior.
- Sensitive content in audit records.
- Model version, decision, verdict, failure, and trace correlation.
- Access controls and retention.
- Whether decisions can be reconstructed without unnecessary sensitive-data storage.

## G. Human oversight
Document separation between mandatory deterministic eligibility rules, semantic matching, model ranking/recommendations, deterministic validation, and human review. Check whether a model can override mandatory rules. Do not claim fairness, bias mitigation, or regulatory compliance without evidence.

## Required report
Save to `docs/audit/06_PHASE_6_AI_GOVERNANCE.md`, including actual execution maps, evidence, tests, gaps, and limitations. No source changes.

## Exit criteria
Laya, classification, guardrails, PII handling, auditability, and human-oversight paths are documented. Wait for approval before fixes.
