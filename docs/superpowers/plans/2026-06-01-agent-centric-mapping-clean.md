# Agent-Centric Mapping Skeleton Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the smallest clean mapping channel that lets an agent fill template text/images from complete structured source/template evidence and page render images, then measure what this skeleton can actually do.

**Architecture:** Keep DataProxy as the upstream parser. Keep existing DocTransAI readers, template analyzers, render plan model, renderers, validators, and reports only where they are directly needed by the skeleton. The new path is: evidence package -> agent decisions -> deterministic validation -> current render plan payload -> renderer.

**Tech Stack:** Python 3.12, `uv`, existing DataProxy bundle contracts, existing DocTransAI template analysis, existing render plan model, existing DOCX renderer, existing LLM client governance.

---

## Hard Boundaries

- Do not modify DataProxy.
- Do not put development-stage labels into new module names, function names, schema names, or prompt names.
- Do not introduce a new render plan schema in this phase.
- Do not rewrite renderers.
- Do not migrate legacy candidate generation, resolver, planner, source instance, or source cluster machinery into the new path.
- Do not run the whole review matrix as the first milestone.
- Do not claim success from tests alone; the skeleton must be judged on a real sample output.

## Required Agent Inputs

The agent receives exactly these four evidence surfaces:

- Source structured content from the upstream DataProxy-derived bundle: records, tables, rows, cells, images, nearby text, diagnostics, provenance, page anchors, bbox, and stable object identifiers when available.
- Source document page render images referenced from the upstream bundle. If source page render images are missing, record an input gap instead of silently pretending text-only evidence is complete.
- Template structured content produced by DocTransAI: slots, placeholders, blank fill regions, tables, repeat regions, template text view, slot addresses, and output targets.
- Template page render images produced by DocTransAI template visual preview. If template page render images are missing, record an input gap.

## Skeleton Acceptance Target

First real target: `word_table_to_docx_record`.

Expected first result:

- No manual global source record selection.
- No legacy candidate resolver deciding what the agent may see.
- Source-existing text required by the template is filled when the agent cites valid source evidence.
- Source-existing images required by the template are placed when the source bundle exposes usable image assets.
- Missing or invalid evidence becomes unresolved with a concrete reason.
- Rendering still goes through the existing render plan model and existing renderer.

## Minimal File Layout

- Create: `src/doctransai/agentic_mapping/context.py`
  Build the four-surface evidence package. This module wraps existing parsed objects; it must not decide mappings.
- Create: `src/doctransai/agentic_mapping/decisions.py`
  Define the minimal agent decision shape for text fills, image placements, and unresolved slots.
- Create: `src/doctransai/agentic_mapping/validator.py`
  Validate that every fill cites source/template evidence present in the evidence package.
- Create: `src/doctransai/agentic_mapping/assembler.py`
  Convert validated decisions into the current render plan payload.
- Create: `src/doctransai/agentic_mapping/mapper.py`
  Send the evidence package to the agent or a deterministic fake decision client.
- Create: `src/doctransai/prompts/agentic_mapping_policy.md`
  State the evidence rules for the agent.
- Create: `src/doctransai/workflows/agentic_conversion.py`
  One clean workflow entrypoint for the skeleton.
- Create: `tests/agentic_mapping/test_context_channel.py`
- Create: `tests/agentic_mapping/test_decisions.py`
- Create: `tests/agentic_mapping/test_validator.py`
- Create: `tests/agentic_mapping/test_assembler.py`
- Create: `tests/workflows/test_agentic_conversion.py`
- Create: `tests/integration/test_agentic_word_table_skeleton.py`

## Chunk 1: Evidence Package Skeleton

**Files:**
- Create: `src/doctransai/agentic_mapping/context.py`
- Create: `tests/agentic_mapping/test_context_channel.py`

- [ ] **Step 1: Write failing context test**

Create a minimal source fixture and template fixture. Assert the context contains:
- `source.structured`
- `source.page_images`
- `source.input_gaps`
- `template.structured`
- `template.page_images`
- `template.input_gaps`

- [ ] **Step 2: Verify no legacy mapping dependency**

The test should fail if `context.py` imports candidate builders, resolver, planner, source instance, or source cluster modules.

- [ ] **Step 3: Implement minimal context builder**

Build a plain dict/dataclass package from existing source/template objects. Preserve facts; do not rank, filter, or choose values.

- [ ] **Step 4: Run focused test**

```bash
uv run pytest tests/agentic_mapping/test_context_channel.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/doctransai/agentic_mapping/context.py tests/agentic_mapping/test_context_channel.py
git commit -m "feat: add agentic evidence package skeleton"
```

## Chunk 2: Minimal Decision Shape

**Files:**
- Create: `src/doctransai/agentic_mapping/decisions.py`
- Create: `tests/agentic_mapping/test_decisions.py`

- [ ] **Step 1: Write failing decision tests**

Cover:
- text fill decision with `slot_id`, `value`, `source_refs`, and `target_ref`
- image placement decision with `slot_id`, `asset_ref`, `source_refs`, and `target_ref`
- unresolved decision with `slot_id` and `reason`
- invalid fill without source refs

- [ ] **Step 2: Implement minimal models**

Use simple dataclasses or typed dict helpers consistent with the current project style. Do not add a JSON schema until the skeleton proves useful.

- [ ] **Step 3: Run focused test**

```bash
uv run pytest tests/agentic_mapping/test_decisions.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/doctransai/agentic_mapping/decisions.py tests/agentic_mapping/test_decisions.py
git commit -m "feat: define agentic mapping decisions"
```

## Chunk 3: Deterministic Validation

**Files:**
- Create: `src/doctransai/agentic_mapping/validator.py`
- Create: `tests/agentic_mapping/test_validator.py`

- [ ] **Step 1: Write failing validator tests**

Cover:
- accepted text fill when source refs exist
- accepted image placement when asset refs exist
- rejected text fill when source refs are missing
- rejected image placement when asset refs are missing
- accepted unresolved decision with reason

- [ ] **Step 2: Implement validator**

The validator checks references only. It must not fuzzy-match missing evidence and must not call legacy mapping modules.

- [ ] **Step 3: Run focused test**

```bash
uv run pytest tests/agentic_mapping/test_validator.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/doctransai/agentic_mapping/validator.py tests/agentic_mapping/test_validator.py
git commit -m "feat: validate agentic mapping decisions"
```

## Chunk 4: Current Render Payload Assembly

**Files:**
- Create: `src/doctransai/agentic_mapping/assembler.py`
- Create: `tests/agentic_mapping/test_assembler.py`

- [ ] **Step 1: Write failing assembler test**

Given validated text/image decisions, assert the assembler emits the current render plan payload with:
- text fills
- image placements
- unresolved slots
- provenance references

- [ ] **Step 2: Implement assembler**

Use existing template target addresses. Do not call the old planner, resolver, or candidate builder.

- [ ] **Step 3: Run focused test**

```bash
uv run pytest tests/agentic_mapping/test_assembler.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/doctransai/agentic_mapping/assembler.py tests/agentic_mapping/test_assembler.py
git commit -m "feat: assemble current render payload from agent decisions"
```

## Chunk 5: Mapper And Prompt

**Files:**
- Create: `src/doctransai/agentic_mapping/mapper.py`
- Create: `src/doctransai/prompts/agentic_mapping_policy.md`
- Create: `tests/agentic_mapping/test_mapper.py`

- [ ] **Step 1: Write failing mapper test with fake decision client**

Fake client receives the evidence package and returns decisions. Assert the mapper parses decisions and does not import legacy mapping modules.

- [ ] **Step 2: Write prompt assertions**

Prompt must state:
- source structured content is evidence
- source page render images are evidence
- template structured content is evidence
- template page render images are evidence
- every fill requires source refs
- unresolved is required when evidence is missing

- [ ] **Step 3: Implement mapper**

Support both a fake decision client for deterministic tests and the existing LLM client for manual runs.

- [ ] **Step 4: Run focused test**

```bash
uv run pytest tests/agentic_mapping/test_mapper.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/doctransai/agentic_mapping/mapper.py src/doctransai/prompts/agentic_mapping_policy.md tests/agentic_mapping/test_mapper.py
git commit -m "feat: add agentic mapper skeleton"
```

## Chunk 6: Single Workflow Skeleton

**Files:**
- Create: `src/doctransai/workflows/agentic_conversion.py`
- Create: `tests/workflows/test_agentic_conversion.py`

- [ ] **Step 1: Write failing workflow test**

Using a fake decision client, assert the workflow:
- reads the source bundle
- analyzes the template
- builds the evidence package
- gets agent decisions
- validates decisions
- assembles the current render payload
- renders output
- writes a compact audit report

- [ ] **Step 2: Implement workflow**

Keep it narrow. This is not a batch audit system and not a migration of the old workflow.

- [ ] **Step 3: Run workflow test**

```bash
uv run pytest tests/workflows/test_agentic_conversion.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/doctransai/workflows/agentic_conversion.py tests/workflows/test_agentic_conversion.py
git commit -m "feat: add agentic conversion skeleton"
```

## Chunk 7: One Real Sample Output

**Files:**
- Create: `tests/integration/test_agentic_word_table_skeleton.py`

- [ ] **Step 1: Write deterministic integration test**

Use `word_table_to_docx_record` with a fake decision client first. Assert source-existing fields are rendered and unresolved fields have reasons.

- [ ] **Step 2: Add optional manual LLM run command**

Only run the real LLM path when credentials are configured. The deterministic test remains the required CI signal.

- [ ] **Step 3: Generate one sample output**

Write output under ignored `outputs/agentic_skeleton/`.

- [ ] **Step 4: Inspect generated document and report**

Classify failures as:
- source context missing
- source page image missing
- template context missing
- template page image missing
- agent decision wrong
- validation rejected valid evidence
- render target missing

- [ ] **Step 5: Run focused tests**

```bash
uv run pytest tests/agentic_mapping tests/workflows/test_agentic_conversion.py tests/integration/test_agentic_word_table_skeleton.py -q
```

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_agentic_word_table_skeleton.py docs
git commit -m "test: prove agentic skeleton on word table sample"
```

## Stop And Decide

After Chunk 7, stop. Do not expand the architecture automatically.

Decision criteria:

- If the skeleton fills the real sample correctly, expand one capability at a time.
- If it fails because the evidence package lacks facts or page images, fix context ingestion before touching mapping logic.
- If it fails because the agent makes poor decisions despite complete evidence, improve prompt/decision format before adding rules.
- If it fails because rendering cannot express the target, then discuss render plan evolution separately.
- If it fails because the old modules are needed, identify exactly which module and why before migrating it.

## Explicit Non-Goals

- No full review matrix in the first skeleton phase.
- No source instance or source cluster migration.
- No candidate packet optimization.
- No legacy resolver fallback.
- No renderer rewrite.
- No direct raw document reading by the agent.
- No broad report system rewrite.
