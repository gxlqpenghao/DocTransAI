# V1-Compatible Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the current V1-compatible DocTransAI path so that real review-set runs produce more auditable reports, clearer traceability grading, and more useful human-review summaries without changing `RenderPlan v1`, renderer semantics, or introducing any `v2` planning behavior.

**Architecture:** Keep DataProxy as the only bundle producer and keep the current `RenderPlan v1`/single-`primary_record` behavior unchanged. The work in this plan strengthens the current V1 path around three surfaces: context-contract consistency (`full_agent_context` vs. legacy convenience fields), report visibility of what the agent actually saw, and traceability grading for generated values. Only after those surfaces are stable do we re-run the real audit matrix and use the results to decide which output fidelity checks are worth adding.

**Tech Stack:** Python 3.12, pytest, JSON Schema, python-docx, openpyxl.

---

## Constraints

- The current workspace is **not** a git worktree, so commit steps cannot run here. Replace each commit step with a short completion note in the execution log unless the repository is reattached to git first.
- Do **not** modify `/Users/paul/Coding/DataProxy`.
- Do **not** introduce `RenderPlan v2`, `plan_unit_kind`, `source_cluster_id`, `repeat_region_instance`, XLSX row cloning, or renderer direct-cluster consumption in this plan.
- `full_agent_context` remains the authoritative agent input contract; legacy top-level fields may remain during migration but must not drift from the full contract.
- `low_traceability_generated` is a **review** downgrade, not a blocking output failure.

## Chunk Exit Gate

Every chunk must end with a redundancy/deprecation audit before it is considered complete.

- [ ] **Audit redundant code introduced or exposed by the chunk**
  Check for duplicate report fields, stale compatibility helpers, old assertions, dead branches, unused imports, and no-longer-needed convenience wrappers.
- [ ] **Delete what is no longer needed immediately**
  Do not defer obvious cleanup to a later chunk if the current chunk made the old code obsolete.
- [ ] **Re-run the chunk's focused tests after cleanup**
  Cleanup is part of the chunk, not a follow-up task.

## File Map

**Likely code changes**

- Modify: `src/doctransai/mapping/agent_resolver.py`
  Purpose: Keep legacy convenience fields consistent with `full_agent_context`.
- Modify: `src/doctransai/reports/conversion_report.py`
  Purpose: Surface full-agent-context status, truncation state, and low-traceability generation markers.
- Modify: `src/doctransai/reports/provenance_report.py`
  Purpose: Carry the same traceability grading into provenance-facing output.
- Modify: `src/doctransai/workflows/v1_conversion.py`
  Purpose: Thread any new report inputs or summary metadata through the workflow.
- Modify: `src/doctransai/workflows/v1_batch_audit.py`
  Purpose: Carry new report/audit-summary fields into batch summaries.
- Modify: `src/doctransai/validation/output_checker.py`
  Purpose: Only after matrix rerun, add targeted fidelity checks justified by real failures.
- Modify: `docs/2026-05-21-doctransai-development-guide.md`
  Purpose: Keep V1 status, quality gates, and accepted boundaries aligned with landed behavior.
- Modify: `V1文档审核集/05_样本配对_Manifest/*.json`
  Purpose: Only if the matrix rerun requires explicit saved-decision or status updates for repeatable audit runs.

**Likely tests**

- Modify: `tests/mapping/test_agent_resolver.py`
- Modify: `tests/reports/test_conversion_report.py`
- Modify: `tests/reports/test_provenance_report.py`
- Modify: `tests/workflows/test_v1_batch_audit.py`
- Modify: `tests/integration/test_v1_conversion_workflow.py`
- Modify: `tests/validation/test_output_checker.py`

## Chunk 1: Full Context Consistency Guards

### Task 1: Add failing tests that lock legacy top-level fields to `full_agent_context`

**Files:**
- Modify: `tests/mapping/test_agent_resolver.py`
- Modify: `tests/integration/test_agent_mapping_preview.py`
- Modify: `tests/integration/test_agent_mapping_resolution.py`

- [ ] **Step 1: Write failing shared-context parity assertions**

Add assertions that:
- `shared_context["source_document_view"] == shared_context["full_agent_context"]["full_source_context"]["document_view"]`
- `shared_context["source_instance_overview"] == shared_context["full_agent_context"]["navigation_context"]["source_instance_overview"]`
- `shared_context["source_cluster_plan"] == shared_context["full_agent_context"]["navigation_context"]["source_cluster_plan"]`

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/mapping/test_agent_resolver.py -q`
Expected: FAIL if any legacy convenience field can drift from `full_agent_context`.

- [ ] **Step 3: Write failing preview/resolution payload parity assertions**

Add assertions that preview/resolution outputs preserve the same parity for duplicated fields.

- [ ] **Step 4: Run the focused tooling tests to verify they fail**

Run: `uv run pytest tests/integration/test_agent_mapping_preview.py tests/integration/test_agent_mapping_resolution.py -q`
Expected: FAIL on missing parity assertions.

### Task 2: Make the legacy convenience fields explicit mirrors of `full_agent_context`

**Files:**
- Modify: `src/doctransai/mapping/agent_resolver.py`
- Modify: `src/doctransai/workflows/agent_mapping_preview.py`
- Modify: `src/doctransai/workflows/agent_mapping_resolution.py`

- [ ] **Step 1: Update `prepare_agent_shared_context()` to source duplicated fields from `full_agent_context`**

Requirements:
- `source_document_view` must mirror `full_source_context.document_view`
- `source_instance_overview` must mirror `navigation_context.source_instance_overview`
- `source_cluster_plan` must mirror `navigation_context.source_cluster_plan`

- [ ] **Step 2: Update preview/resolution payload construction only if required**

Requirements:
- Avoid re-deriving any duplicated context in the workflow layer
- Keep `full_agent_context` as the only authoritative assembled object

- [ ] **Step 3: Run the focused tests**

Run: `uv run pytest tests/mapping/test_agent_resolver.py tests/integration/test_agent_mapping_preview.py tests/integration/test_agent_mapping_resolution.py -q`
Expected: PASS

- [ ] **Step 4: Record completion**

Because this workspace has no `.git`, record: `Chunk 1 completed without git commit`.

## Chunk 2: Report Full Agent Context Visibility

### Task 3: Add failing report tests for full-context visibility

**Files:**
- Modify: `tests/reports/test_conversion_report.py`
- Modify: `tests/integration/test_v1_conversion_workflow.py`
- Modify: `tests/workflows/test_v1_batch_audit.py`

- [ ] **Step 1: Write failing conversion-report assertions**

Add assertions that conversion output exposes, at minimum:
- `full_agent_context_schema_version`
- `full_source_record_count`
- `full_source_image_asset_count`
- `full_source_diagnostic_count`
- truncation state (`records_truncated`, `diagnostics_truncated`, or equivalent)
- `source_instance_id`
- repeat-region cluster-hint presence/count

- [ ] **Step 2: Run the focused report tests to verify they fail**

Run: `uv run pytest tests/reports/test_conversion_report.py tests/integration/test_v1_conversion_workflow.py -q`
Expected: FAIL because the report does not expose the new fields yet.

- [ ] **Step 3: Write failing batch-summary assertions**

Add assertions that batch summaries/csv/json can carry the same report-level audit fields or a compact derivative of them.

- [ ] **Step 4: Run the batch-audit tests to verify they fail**

Run: `uv run pytest tests/workflows/test_v1_batch_audit.py -q`
Expected: FAIL on missing summary fields.

### Task 4: Surface full-context status in reports and batch summaries

**Files:**
- Modify: `src/doctransai/reports/conversion_report.py`
- Modify: `src/doctransai/workflows/v1_conversion.py`
- Modify: `src/doctransai/workflows/v1_batch_audit.py`

- [ ] **Step 1: Thread the full-context status into conversion reporting**

Requirements:
- Use existing plan/workflow context where possible
- Avoid dumping the full context object into the report
- Expose a compact audit-facing summary only

- [ ] **Step 2: Add the same summary to batch outputs**

Requirements:
- Keep CSV compact and human-readable
- Preserve JSON richness for later audit tooling

- [ ] **Step 3: Run the focused tests**

Run: `uv run pytest tests/reports/test_conversion_report.py tests/integration/test_v1_conversion_workflow.py tests/workflows/test_v1_batch_audit.py -q`
Expected: PASS

- [ ] **Step 4: Record completion**

Because this workspace has no `.git`, record: `Chunk 2 completed without git commit`.

## Chunk 3: Low-Traceability Generated Value Grading

### Task 5: Add failing tests for low-traceability generation markers

**Files:**
- Modify: `tests/reports/test_conversion_report.py`
- Modify: `tests/reports/test_provenance_report.py`
- Modify: `tests/integration/test_v1_conversion_workflow.py`

- [ ] **Step 1: Write failing conversion-report assertions**

Add assertions that when a fill is generated from broad document context without precise record/table/cell/image/page provenance:
- `decision_kind` still reflects generated output
- traceability is downgraded to `low_traceability_generated` (or the chosen exact field name)
- `review_required` becomes true
- output is not marked as blocking solely because of low traceability

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/reports/test_conversion_report.py tests/reports/test_provenance_report.py -q`
Expected: FAIL because low-traceability grading is not implemented yet.

### Task 6: Implement low-traceability review grading without blocking output

**Files:**
- Modify: `src/doctransai/reports/conversion_report.py`
- Modify: `src/doctransai/reports/provenance_report.py`

- [ ] **Step 1: Define the grading rule**

Requirements:
- If a generated value cannot be precisely tied back to record/table/cell/image/page-anchor evidence, mark it as low traceability
- Keep the output fill
- Force review layering, not blocking failure

- [ ] **Step 2: Implement the grading in report serialization**

Requirements:
- Preserve current `decision_kind`
- Add an explicit traceability field or equivalent diagnostic
- Keep unresolved and hard errors semantically separate

- [ ] **Step 3: Run the focused tests**

Run: `uv run pytest tests/reports/test_conversion_report.py tests/reports/test_provenance_report.py tests/integration/test_v1_conversion_workflow.py -q`
Expected: PASS

- [ ] **Step 4: Record completion**

Because this workspace has no `.git`, record: `Chunk 3 completed without git commit`.

## Chunk 4: Real Review-Set Matrix Rerun

### Task 7: Prepare a reproducible real-matrix rerun target

**Files:**
- Modify: `V1文档审核集/05_样本配对_Manifest/v1_cases.json`
- Modify: `V1文档审核集/05_样本配对_Manifest/v1_expanded_matrix.json`
- Modify: `docs/2026-05-21-doctransai-development-guide.md`

- [ ] **Step 1: Define which manifests are the current real review-set baseline**

Requirements:
- Use the latest bundle-compatible manifest set
- Prefer agent-enabled paths where that reflects the true V1 mainline
- If saved decision payloads are needed for repeatable reruns, document exactly where they live

- [ ] **Step 2: Add/update any manifest-only metadata needed for rerun auditability**

Requirements:
- Do not smuggle in `v2` semantics
- Keep the manifests still valid for current `v1_batch_audit`

- [ ] **Step 3: Run manifest-loading tests**

Run: `uv run pytest tests/workflows/test_v1_batch_audit.py::test_load_v1_case_manifest_resolves_relative_paths -q`
Expected: PASS

### Task 8: Execute the real-matrix rerun and collect audit artifacts

**Files:**
- Runtime outputs only under `outputs/`

- [ ] **Step 1: Run the selected matrix**

Run an agreed batch command using `run_v1_batch_audit(...)` or the equivalent Python entry.
Expected artifacts per case:
- output document
- conversion report
- provenance report
- performance report

- [ ] **Step 2: Produce a compact quality summary**

Requirements:
- Summarize unresolved counts, render-clean vs review-required, low-traceability-generated counts, and truncation indicators
- Keep it separate from code changes if only output artifacts are produced

- [ ] **Step 3: Record completion**

Because this workspace has no `.git`, record the output directory and summary artifact paths.

## Chunk 5: Post-Matrix Output Fidelity Hardening

### Task 9: Convert real rerun findings into targeted fidelity checks

**Files:**
- Modify: `src/doctransai/validation/output_checker.py`
- Modify: `tests/validation/test_output_checker.py`
- Modify: `docs/2026-05-21-doctransai-development-guide.md`

- [ ] **Step 1: Review the real matrix outputs and select only recurring, high-signal fidelity failures**

Requirements:
- Do not add speculative checks
- Use only failures observed in the rerun outputs

- [ ] **Step 2: Write failing tests for the selected checks**

Examples:
- template structure drift
- style drift
- image target mismatch
- repeated residual media symptoms

- [ ] **Step 3: Run the focused tests to verify failure**

Run: `uv run pytest tests/validation/test_output_checker.py -q`
Expected: FAIL on the new fidelity assertions.

- [ ] **Step 4: Implement only the justified checks**

Requirements:
- Keep them generic
- Do not add domain-specific or template-family-specific rules
- Do not change renderer behavior in this chunk

- [ ] **Step 5: Run the focused tests**

Run: `uv run pytest tests/validation/test_output_checker.py -q`
Expected: PASS

- [ ] **Step 6: Record completion**

Because this workspace has no `.git`, record: `Chunk 5 completed without git commit`.

## Final Verification

- [ ] Run: `uv run pytest tests/mapping/test_agent_resolver.py tests/integration/test_agent_mapping_preview.py tests/integration/test_agent_mapping_resolution.py -q`
- [ ] Run: `uv run pytest tests/reports/test_conversion_report.py tests/reports/test_provenance_report.py tests/integration/test_v1_conversion_workflow.py -q`
- [ ] Run: `uv run pytest tests/workflows/test_v1_batch_audit.py tests/validation/test_output_checker.py -q`
- [ ] Run: `uv run pytest -q`

## Execution Notes

- Stay inside `v1` compatibility. No `RenderPlan v2`, no multi-instance renderer behavior, no XLSX region materialization.
- Treat low-traceability generation as a review downgrade, not as a blocking error by default.
- Use the real review-set rerun to justify any new fidelity checks; do not guess in advance.

## Completion Log

- Chunk 1 completed without git commit: legacy convenience fields now mirror `full_agent_context`; focused tests passed.
- Chunk 2 completed without git commit: conversion reports, performance summaries, and batch summaries now include compact `full_agent_context_summary`; focused tests passed.
- Chunk 3 completed without git commit: `low_traceability_generated` review grading added for agent-generated values without precise non-generated provenance; focused tests passed.
- Chunk 4 completed without git commit: real matrix rerun output is under `outputs/v1_audit_runs/2026-05-27_v1_hardening_expanded_matrix_default`; compact audit artifacts are `quality_audit_summary.md` and `quality_audit_summary.json`.
- Chunk 5 completed without git commit: no new output fidelity rule was added because the rerun did not reveal a new generic, recurring fidelity failure beyond existing checker coverage.
- Final verification completed: `uv run pytest -q` -> `258 passed in 5.40s`.
- Post-review payload governance completed without git commit: oversized default-agent request bodies are preflight-blocked before HTTP, downgraded to unresolved, and surfaced in conversion/batch summaries through estimated bytes, configured limit, within-limit status, and preflight-blocked status.
- Post-review payload governance follow-up completed without git commit: the same preflight rule now applies to injected `decision_client` wrappers, and batch summaries include matrix-level `agent_input_payload_governance` counts for over-limit, preflight-blocked, and provider request-body-limit failures.
- Post-review payload governance second follow-up completed without git commit: repair retry requests now run the same preflight check, conversion summaries preserve real `source_overview` truncation state, and the expanded-matrix `quality_audit_summary.json` now has a top-level `agent_input_payload_governance` object matching the Markdown summary.
- Audit artifact refresh completed without git commit: `outputs/v1_audit_runs/2026-05-28_v1_hardening_expanded_matrix_current` is the current V1 matrix audit entrypoint. It shows 14 executed / 0 failed, `provider_request_body_limit_failure_count=0`, and `scitech_pdf_to_docx_innovation_form_agent` is now a preflight-blocked review case rather than a provider HTTP failure.
- Blocking issue review table completed without git commit: batch audit now writes `blocking_issue_summary.md/json/csv`; the refreshed 2026-05-28 matrix has 9 blocking cases, including 1 agent payload preflight-blocked case and 9 output-check/unresolved review cases.
