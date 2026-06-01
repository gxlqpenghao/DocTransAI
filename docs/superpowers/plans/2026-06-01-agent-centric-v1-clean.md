# V1 Agent-Centric Mapping Clean Rebuild Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the V1 mapping layer so template slots are filled by an agent using complete source/template context and validated provenance, instead of being gated by the legacy `primary_record -> candidates -> resolver` path.

**Architecture:** Keep DataProxy as the upstream parser and keep existing DocTransAI readers, template analyzers, renderers, validators, and reports where they are stable. Replace the mapping decision center with a single agent-centric flow: context package -> agent slot decisions -> deterministic validation -> `RenderPlan v1` assembly. Legacy rule-first mapping remains reference-only until explicitly needed as a deterministic hint provider.

**Tech Stack:** Python 3.12, `uv`, `python-docx`, `openpyxl`, existing DataProxy bundle contracts, existing `RenderPlan v1`, existing LLM client with request-size governance.

---

## Non-Negotiable Boundaries

- Do not modify DataProxy.
- Do not implement `RenderPlan v2`.
- Do not make renderers read bundles, clusters, or agent context directly.
- Do not use `primary_record` as a required global mapping gate.
- Do not let rule-generated candidates decide what the agent is allowed to see.
- Do not accept agent decisions without provenance validation.
- Do not treat navigation/index summaries as evidence.
- Do not claim V1 success unless source-existing text/images required by the template are filled or explicitly marked unresolved with a defensible evidence reason.

## Success Target

The first hard acceptance case is `word_table_to_docx_record`.

Expected behavior:

- No manual `primary_record_id`.
- The agent can use the DataProxy structured source view and template view to fill source-existing fields such as project name, hazard type, hazard description, rectification requirement, rectification deadline, and inspection date.
- Every filled value has a source reference that resolves to a real DataProxy-derived object.
- Missing images remain unresolved only when the source bundle has no usable image asset.
- Output still uses existing `RenderPlan v1` and existing DOCX renderer.

## Files And Responsibilities

- Reuse: `src/doctransai/data_layer/*`
  Read and validate DataProxy bundle sidecars.
- Reuse: `src/doctransai/source_model/*`
  Adapt parsed bundle into DocTransAI source objects; may add read-only helpers, but do not add mapping decisions here.
- Reuse: `src/doctransai/templates/*`
  Analyze template slots, placeholders, blank regions, repeat regions, and template visual previews.
- Reuse: `src/doctransai/llm/client.py`
  Keep request body and input-length governance.
- Reuse: `src/doctransai/models/render_plan.py`
  Continue emitting `RenderPlan v1`.
- Create: `src/doctransai/agentic_context/models.py`
  Typed data model for the source/template context package given to the agent.
- Create: `src/doctransai/agentic_context/builder.py`
  Build complete source/template context and page-image references without rule-first filtering.
- Create: `src/doctransai/agentic_mapping/decision_models.py`
  Typed model for agent slot decisions.
- Create: `src/doctransai/agentic_mapping/mapper.py`
  Invoke the agent and parse decisions.
- Create: `src/doctransai/agentic_mapping/validator.py`
  Validate values, assets, and source references before rendering.
- Create: `src/doctransai/agentic_mapping/render_plan_assembler.py`
  Convert validated decisions into `RenderPlan v1`.
- Create: `src/doctransai/prompts/agentic_mapping_policy.md`
  Prompt contract for agent-centric mapping.
- Create: `src/doctransai/workflows/v1_agentic_conversion.py`
  A clean workflow entrypoint for the rebuilt V1 path.
- Test: `tests/agentic_context/*`
- Test: `tests/agentic_mapping/*`
- Test: `tests/workflows/test_v1_agentic_conversion.py`

## Chunk 1: Context Package Contract

**Files:**
- Create: `src/doctransai/agentic_context/models.py`
- Create: `src/doctransai/agentic_context/builder.py`
- Create: `tests/agentic_context/test_context_builder.py`

- [ ] **Step 1: Write failing tests for complete source context**

Test a small synthetic bundle-derived `SourceModel` with:
- one table-level object
- one table row with values
- one image asset with page anchor
- one diagnostic

Expected context includes records, tables, cells, images, diagnostics, provenance refs, page anchors, and object index.

- [ ] **Step 2: Write failing tests for complete template context**

Test a DOCX template analysis fixture with text slots, image slots, repeat regions, and template visual page references.

- [ ] **Step 3: Implement context models**

Define:
- `AgenticSourceContext`
- `AgenticTemplateContext`
- `AgenticMappingContext`
- `ContextObjectRef`
- `PageVisualRef`

Keep models simple dataclasses or pydantic-free dict builders, matching current project style.

- [ ] **Step 4: Implement context builder**

Build context from existing `SourceModel` and `TemplateModel`.
Do not use `primary_record`.
Do not call legacy candidate builder.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/agentic_context/test_context_builder.py -q
```

Expected: all new context tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/doctransai/agentic_context tests/agentic_context
git commit -m "feat: add agentic mapping context package"
```

## Chunk 2: Agent Decision Contract

**Files:**
- Create: `src/doctransai/agentic_mapping/decision_models.py`
- Create: `contracts/doctransai/agentic_mapping_decision_v1.schema.json`
- Create: `tests/agentic_mapping/test_decision_models.py`

- [ ] **Step 1: Write failing schema/model tests**

Cover:
- text fill decision
- image placement decision
- unresolved decision
- invalid decision missing source refs
- invalid decision using navigation-only ref as evidence

- [ ] **Step 2: Implement decision model**

Decision fields:
- `slot_id`
- `decision_type`: `text_fill`, `image_placement`, `unresolved`
- `value`
- `asset_id`
- `source_refs`
- `confidence`
- `reason`
- `unresolved_reason`

- [ ] **Step 3: Implement JSON schema**

Schema must reject decisions that contain neither fill data nor unresolved reason.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/agentic_mapping/test_decision_models.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/doctransai/agentic_mapping/decision_models.py contracts/doctransai/agentic_mapping_decision_v1.schema.json tests/agentic_mapping/test_decision_models.py
git commit -m "feat: define agentic mapping decisions"
```

## Chunk 3: Deterministic Decision Validator

**Files:**
- Create: `src/doctransai/agentic_mapping/validator.py`
- Create: `tests/agentic_mapping/test_validator.py`

- [ ] **Step 1: Write failing validation tests**

Cover:
- accepted text value with exact source object ref
- accepted image asset id that exists
- rejected value whose source ref does not exist
- rejected image asset id that does not exist
- rejected fill that cites only navigation context
- unresolved decision is accepted with reason

- [ ] **Step 2: Implement validator**

Validator must return:
- accepted decisions
- rejected decisions
- diagnostics

No rendering should happen here.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/agentic_mapping/test_validator.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/doctransai/agentic_mapping/validator.py tests/agentic_mapping/test_validator.py
git commit -m "feat: validate agentic mapping decisions"
```

## Chunk 4: RenderPlan v1 Assembler

**Files:**
- Create: `src/doctransai/agentic_mapping/render_plan_assembler.py`
- Create: `tests/agentic_mapping/test_render_plan_assembler.py`

- [ ] **Step 1: Write failing assembler tests**

Given validated text and image decisions, assert generated `RenderPlan v1` has:
- expected `text_fills`
- expected `image_placements`
- expected `unresolved_slots`
- expected provenance refs
- no `RenderPlan v2` fields

- [ ] **Step 2: Implement assembler**

Use existing `TemplateSlot.address` to create render targets.
Do not call old resolver.
Do not call old planner.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/agentic_mapping/test_render_plan_assembler.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/doctransai/agentic_mapping/render_plan_assembler.py tests/agentic_mapping/test_render_plan_assembler.py
git commit -m "feat: assemble render plan from agent decisions"
```

## Chunk 5: Agent Mapper And Prompt

**Files:**
- Create: `src/doctransai/agentic_mapping/mapper.py`
- Create: `src/doctransai/prompts/agentic_mapping_policy.md`
- Create: `tests/agentic_mapping/test_mapper.py`

- [ ] **Step 1: Write failing mapper tests with fake decision client**

Fake client returns valid decisions for a small template/source fixture.
Assert mapper parses them and does not invoke legacy candidate builders.

- [ ] **Step 2: Write prompt assertions**

Prompt must state:
- source context and template context are evidence
- page render images are evidence when available
- navigation context is index only
- fill only if evidence exists
- return unresolved instead of inventing
- every fill requires source refs

- [ ] **Step 3: Implement mapper**

Mapper should:
- build request payload from `AgenticMappingContext`
- use existing LLM client governance
- parse decisions
- return unresolved decisions on preflight block

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/agentic_mapping/test_mapper.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/doctransai/agentic_mapping/mapper.py src/doctransai/prompts/agentic_mapping_policy.md tests/agentic_mapping/test_mapper.py
git commit -m "feat: add agentic mapper"
```

## Chunk 6: Clean V1 Workflow

**Files:**
- Create: `src/doctransai/workflows/v1_agentic_conversion.py`
- Create: `tests/workflows/test_v1_agentic_conversion.py`

- [ ] **Step 1: Write failing workflow test**

Use a fake decision client and the existing V1 DOCX template.
Assert:
- bundle is read
- template is analyzed
- agent decisions are validated
- render plan is assembled
- renderer runs
- conversion/provenance reports are emitted

- [ ] **Step 2: Implement workflow**

Workflow stages:
- read bundle
- adapt source corpus
- filter source file if supplied
- analyze/materialize template
- build agentic context
- call agent mapper
- validate decisions
- assemble `RenderPlan v1`
- render
- validate output
- report

- [ ] **Step 3: Run workflow test**

```bash
uv run pytest tests/workflows/test_v1_agentic_conversion.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/doctransai/workflows/v1_agentic_conversion.py tests/workflows/test_v1_agentic_conversion.py
git commit -m "feat: add agentic v1 conversion workflow"
```

## Chunk 7: Acceptance Case Harness

**Files:**
- Create: `tests/integration/test_agentic_word_table_acceptance.py`
- Modify: `src/doctransai/workflows/v1_batch_audit.py` only if a separate agentic entrypoint flag is needed.

- [ ] **Step 1: Write failing acceptance test**

Target: `word_table_to_docx_record`.

Use a deterministic fake agent decision payload that fills source-existing values from the Word table source. Assert fields are rendered and provenance exists.

- [ ] **Step 2: Add minimal harness support**

If needed, add a flag such as `mapping_mode="agentic"` without altering legacy default behavior.

- [ ] **Step 3: Run acceptance test**

```bash
uv run pytest tests/integration/test_agentic_word_table_acceptance.py -q
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_agentic_word_table_acceptance.py src/doctransai/workflows/v1_batch_audit.py
git commit -m "test: cover agentic word table acceptance"
```

## Chunk 8: Matrix Rerun And Decision

**Files:**
- No production file expected unless test evidence exposes a bug.

- [ ] **Step 1: Run focused tests**

```bash
uv run pytest tests/agentic_context tests/agentic_mapping tests/workflows/test_v1_agentic_conversion.py -q
```

- [ ] **Step 2: Run full tests**

```bash
uv run pytest -q
```

- [ ] **Step 3: Run V1 matrix in agentic mode**

Use a new output directory under ignored `outputs/`.

- [ ] **Step 4: Inspect reports**

Minimum acceptance:
- `word_table_to_docx_record` fills source-existing text.
- No provider 400 failures.
- Rejected decisions are explained by validator diagnostics.
- Existing renderer behavior remains unchanged.

- [ ] **Step 5: Commit final harness/docs update**

```bash
git add docs tests src
git commit -m "docs: document agentic v1 acceptance results"
```

## Stop Conditions

Stop and reassess if:

- The agent cannot cite stable source refs for filled values.
- Page render images are unavailable from DataProxy and cannot be referenced cleanly.
- Validator needs fuzzy source matching to accept values.
- Renderer changes become necessary before `word_table_to_docx_record` works.
- The implementation starts reintroducing `primary_record` as a required mapping gate.

## Current Non-Goal

Do not solve multi-instance `RenderPlan v2`, XLSX row-band materialization, or arbitrary long-document autonomous delivery in this rebuild. The only current goal is a clean V1 mapping path that fills source-existing template content through agent decisions and deterministic validation.
