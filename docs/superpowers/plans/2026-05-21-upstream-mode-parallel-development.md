# DataProxy Upstream Mode Parallel Development Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development to implement this plan. Spawn fresh worker subagents by lane, keep write sets disjoint, and run review agents after each wave. Current V1 may import/call DataProxy only through `src/doctransai/upstream/dataproxy/`; never modify files under `/Users/paul/Coding/DataProxy`.

**Goal:** Build DocTransAI's V1 validation path from DataProxy `ParsedDocumentBundle v0` to `TemplateModel`, `RenderPlan`, renderers, and reports, while keeping future standalone ingestion positions reserved.

**Architecture:** DataProxy remains the upstream bundle producer. DocTransAI starts at `data_layer`, adapts raw bundle records into strong source models, analyzes templates, maps fields/images into an auditable `RenderPlan`, renders docx/xlsx/pdf outputs, then writes conversion and provenance reports.
Long-term mapping direction is constrained by `docs/2026-05-21-generic-mapping-principles.md`: no domain field packs in the core path, deterministic structural narrowing first, LLM only for batched ambiguity resolution.

**Tech Stack:** Python 3.12, JSON Schema, python-docx, openpyxl, Pillow, optional pypdf/reportlab for PDF output, pytest.

---

## Execution Mode

Run this as a parallel subagent program, not a sequential feature crawl.

- Controller keeps the contract files stable and resolves interface disputes.
- Worker subagents own disjoint file sets and do not revert each other's edits.
- Review subagents check spec compliance and code quality after each wave.
- DataProxy is upstream-only. If a worker finds a DataProxy issue, they create a DocTransAI note/report item and stop short of editing DataProxy.

## Critical Path

```text
P0 Shared Contracts
  -> P1A Source Model Adapter
  -> P2 Mapping + RenderPlan
  -> P3 Renderer + Reports

P1B Template Analyzer runs in parallel with P1A.
P1C DataProxy upstream runner and issue reporting runs in parallel with P1A/P1B.
P1D Validation/report gates start after P0 and deepen after P2/P3.
```

## Reserved Versus Active Areas

Active V1 areas:

- `src/doctransai/upstream/dataproxy/`
- `src/doctransai/data_layer/`
- `src/doctransai/source_model/`
- `src/doctransai/templates/`
- `src/doctransai/mapping/`
- `src/doctransai/models/`
- `src/doctransai/renderers/`
- `src/doctransai/reports/`
- `src/doctransai/validation/`

Reserved for later standalone delivery:

- `src/doctransai/ingestion/`
- `src/doctransai/canonical/`
- `src/doctransai/ingestion/asset_pack/`

Do not expand the reserved areas except for compatibility stubs already present.

## Wave P0: Shared Contracts

**Purpose:** Freeze the interfaces that all lanes share.

**Worker:** contract-owner

**Files:**

- Create: `src/doctransai/models/diagnostics.py`
- Create: `src/doctransai/models/source.py`
- Create: `src/doctransai/models/template.py`
- Create: `src/doctransai/models/mapping.py`
- Create: `src/doctransai/models/render_plan.py`
- Create: `contracts/doctransai/render_plan_v1.schema.json`
- Modify: `src/doctransai/models/__init__.py`
- Test: `tests/models/test_render_plan.py`
- Test: `tests/contracts/test_render_plan_schema.py`

**Contracts To Define:**

- `SourceDocument`, `SourceRecord`, `SourceValue`, `SourceImageAsset`, `QualityDiagnostic`
- `TemplateModel`, `TemplateSlot`, `SlotAddress`, `RepeatRegion`, `HeaderDrivenRegion`
- `FieldCandidate`, `ImageCandidate`, `ResolvedSlot`, `UnresolvedSlot`, `ResolverDecision`
- `RenderPlan`, `TextFill`, `ImagePlacement`, `RowPlan`, `PlanDiagnostic`, `ProvenanceRef`

**Acceptance:**

- `RenderPlan` JSON round-trips without losing provenance.
- Schema validates a minimal text fill, image placement, unresolved slot, and diagnostic.
- No DataProxy import in `models`.

## Wave P1: Parallel Builders

### Lane A: Source Model Adapter

**Worker:** source-model-worker

**Files:**

- Create: `src/doctransai/source_model/__init__.py`
- Create: `src/doctransai/source_model/adapter.py`
- Create: `tests/source_model/test_adapter.py`
- Modify: `src/doctransai/data_layer/models.py`

**Scope:**

- Convert `SourceCorpus` raw records into strong `SourceModel`.
- Index documents, evidence, tables, cell ranges, sheets, visual assets, diagnostics.
- Build xlsx row records from `cell_ranges`.
- Build table records from `table_units` defensively.
- Resolve image asset paths from `source_ref`, `source_checksum`, and bundle directory.

**Acceptance:**

- Real smoke test on `artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json` reports 4 docs, 17 evidence, 2 tables, 11 cell ranges, 25 visual assets, 29 diagnostics.
- Missing optional sidecars return empty collections.
- Missing required ids raise `SourceModelAdaptationError`.

### Lane B: Template Analyzer

**Worker:** template-worker

**Files:**

- Create: `src/doctransai/templates/models.py`
- Create: `src/doctransai/templates/placeholders.py`
- Create: `src/doctransai/templates/analyzers/base.py`
- Create: `src/doctransai/templates/analyzers/docx.py`
- Create: `src/doctransai/templates/analyzers/xlsx.py`
- Create: `src/doctransai/templates/analyzers/pdf.py`
- Modify: `src/doctransai/templates/__init__.py`
- Modify: `src/doctransai/templates/analyzers/__init__.py`
- Test: `tests/templates/test_placeholders.py`
- Test: `tests/templates/test_docx_analyzer.py`
- Test: `tests/templates/test_xlsx_analyzer.py`
- Test: `tests/templates/test_pdf_analyzer.py`

**Scope:**

- Parse `{字段}` placeholders, including cross-run placeholders.
- Classify image slots by field names containing `照片/图片/photo/image`.
- Identify xlsx header-driven regions and image columns.
- Emit PDF form fields or diagnostics; do not invent slots for plain PDFs.

**Acceptance:**

- V1 docx templates match known occurrence/unique field counts.
- `安全检查台账模版.xlsx` identifies title row, header row, sample rows, and photo columns.
- Template analyzer does not import DataProxy.

### Lane C: DataProxy Upstream Boundary

**Worker:** upstream-worker

**Files:**

- Create: `src/doctransai/upstream/dataproxy/runner.py`
- Create: `src/doctransai/upstream/dataproxy/issue_report.py`
- Modify: `src/doctransai/upstream/dataproxy/__init__.py`
- Test: `tests/upstream/test_dataproxy_runner.py`
- Test: `tests/upstream/test_issue_report.py`

**Scope:**

- Provide a single allowed boundary for DataProxy imports/calls.
- Support resolving DataProxy via `PYTHONPATH=/Users/paul/Coding/DataProxy/src` or explicit config.
- Produce a clear failure if DataProxy is unavailable.
- Create structured issue reports for upstream defects.

**Acceptance:**

- Tests can mock DataProxy import/call without requiring DataProxy to be installed.
- No worker writes to `/Users/paul/Coding/DataProxy`.
- Policy test still passes.

### Lane D: Validation Foundations

**Worker:** validation-worker

**Files:**

- Create: `src/doctransai/validation/bundle_gate.py`
- Create: `src/doctransai/validation/output_checker.py`
- Modify: `src/doctransai/validation/__init__.py`
- Test: `tests/validation/test_bundle_gate.py`
- Test: `tests/validation/test_output_checker.py`

**Scope:**

- Gate bundle diagnostics before mapping.
- Check unresolved slots, placeholder residue, missing assets, and unapplied operations.
- Start with common checks; format-specific checks deepen after renderers land.

**Acceptance:**

- Bundle with severe diagnostics can be configured to warn or fail.
- Placeholder residue like `{隐患描述}` is detected in generated files/strings.

## Wave P2: Mapping And Planning

### Lane E: Generic Structural Candidates

**Worker:** mapping-field-worker

**Files:**

- Create: `src/doctransai/mapping/__init__.py`
- Create: `src/doctransai/mapping/type_inference.py`
- Create: `src/doctransai/mapping/structural_candidates.py`
- Test: `tests/mapping/test_type_inference.py`
- Test: `tests/mapping/test_structural_candidates.py`

**Scope:**

- Infer generic slot/value shapes.
- Generate structural text candidates from SourceModel records.
- Avoid domain field packs in the main path.

**Acceptance:**

- Generic slots generate candidates from row structure and value shape.
- Each candidate carries provenance and confidence base.

### Lane F: Image Mapper

**Worker:** mapping-image-worker

**Files:**

- Create: `src/doctransai/mapping/image_mapper.py`
- Test: `tests/mapping/test_image_mapper.py`

**Scope:**

- Map `隐患照片/整改照片/复查照片` slots to visual assets.
- Prefer `row_index/column_index/header` over weak `related_evidence_ids`.
- Resolve missing image files as unresolved diagnostics, not silent skips.

**Acceptance:**

- K/T/Y-style photo columns map to correct roles for xlsx records.
- Cross-row weak visual links do not duplicate images into wrong records.

### Lane G: Resolver And RenderPlan Planner

**Worker:** planner-worker

**Files:**

- Create: `src/doctransai/mapping/resolver.py`
- Create: `src/doctransai/mapping/planner.py`
- Test: `tests/mapping/test_resolver.py`
- Test: `tests/mapping/test_planner.py`
- Test: `tests/integration/test_mapping_render_plan_from_dataproxy_bundle.py`

**Scope:**

- Rank candidates: exact field/alias > same record row > table context > text fact > weak context.
- Emit unresolved for missing, ambiguous, low-confidence, type mismatch, missing image file.
- Produce `RenderPlan` JSON only; no renderer behavior here.

**Acceptance:**

- Integration test creates RenderPlan from real DataProxy bundle and synthetic TemplateModel without writing output docs.
- Every fill/image has provenance or explicit generated/system marker.

## Wave P3: Renderers, Reports, Output Checks

### Lane H: Renderer Core And Image Placement

**Worker:** renderer-core-worker

**Files:**

- Create: `src/doctransai/renderers/models.py`
- Create: `src/doctransai/renderers/base.py`
- Create: `src/doctransai/renderers/image_placement.py`
- Modify: `src/doctransai/renderers/__init__.py`
- Test: `tests/renderers/test_image_placement.py`

**Scope:**

- Define `Renderer` protocol and `RenderResult`.
- Resolve DataProxy `source_ref` paths.
- Define sizing policies: `fit_cell`, `contain`, `original`, `max_width`.

**Acceptance:**

- Asset path resolver supports absolute path, `bundle_dir/source_ref`, and `bundle_dir/parsed/{checksum}/{source_ref}`.
- Missing assets produce diagnostic.

### Lane I: Format Renderers

**Worker group:** docx-render-worker, xlsx-render-worker, pdf-render-worker

**Files:**

- Create: `src/doctransai/renderers/docx.py`
- Create: `src/doctransai/renderers/xlsx.py`
- Create: `src/doctransai/renderers/pdf.py`
- Create: `src/doctransai/renderers/pipeline.py`
- Test: `tests/renderers/test_docx_renderer.py`
- Test: `tests/renderers/test_xlsx_renderer.py`
- Test: `tests/renderers/test_pdf_renderer.py`

**Scope:**

- DOCX: placeholder replacement, table-cell replacement, image insertion, cross-run handling.
- XLSX: cell fills, row style copy, image insertion, preserve widths/heights/merged cells.
- PDF: first thin pass for form fields or overlay diagnostics.

**Acceptance:**

- Output files open with their libraries.
- Renderer does not select fields; it only executes `RenderPlan`.
- Unapplied operations are reported.

### Lane J: Reports

**Worker:** reports-worker

**Files:**

- Create: `src/doctransai/reports/conversion_report.py`
- Create: `src/doctransai/reports/provenance_report.py`
- Modify: `src/doctransai/reports/__init__.py`
- Test: `tests/reports/test_conversion_report.py`
- Test: `tests/reports/test_provenance_report.py`

**Scope:**

- Write machine-readable `conversion_report.json`.
- Write human-readable `provenance_report.md`.
- Include unresolved slots, diagnostics, source evidence ids, asset ids, source paths, locators.

**Acceptance:**

- Reports can be generated from synthetic RenderPlan + RenderResult.
- Report includes every fill/image/unresolved item.

## Wave P4: Integration Demo

**Worker:** integration-worker

**Files:**

- Create: `src/doctransai/workflows/__init__.py`
- Create: `src/doctransai/workflows/v1_conversion.py`
- Create: `tests/integration/test_v1_conversion_workflow.py`
- Modify: `src/doctransai/cli.py`

**Scope:**

- Wire existing DataProxy bundle artifact to SourceModel, TemplateModel, Mapping, RenderPlan, Renderer, Reports.
- Start with one xlsx row to one docx template.
- CLI can accept an existing `parsed_document_bundle.json` and a template path.

**Acceptance:**

- End-to-end smoke generates one output docx and reports without modifying DataProxy.
- Failing/missing fields are explicit in unresolved output.
- `uv run pytest -q` passes.

## Review Protocol

After each wave:

1. Spec reviewer checks the worker stayed inside owned files and met lane acceptance.
2. Code-quality reviewer checks cohesion, tests, no accidental DataProxy writes, and no parser logic in mapping/renderers.
3. Controller runs:

```bash
uv run pytest -q
```

4. If a DataProxy issue is found, create/update a DocTransAI issue report and stop short of upstream edits.

## Parallel Start Set

Start these immediately after approving this plan:

- contract-owner
- source-model-worker
- template-worker
- upstream-worker
- validation-worker

Start these once P0 contracts are stable:

- mapping-field-worker
- mapping-image-worker
- planner-worker
- renderer-core-worker
- reports-worker

Start renderers after renderer core is available:

- docx-render-worker
- xlsx-render-worker
- pdf-render-worker

Start integration after SourceModel + TemplateModel + RenderPlan + at least DOCX renderer are green.
