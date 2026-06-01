# Full Bundle Agent Context And Cluster Planning Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade DocTransAI's agent input from compact per-slot context to a versioned full bundle-derived context, then use that foundation to prepare read-only cluster-aware planning without changing the current default RenderPlan behavior.

**Architecture:** Keep DataProxy as the only bundle producer. DocTransAI should build a versioned `doctransai_full_agent_context_v1` object from bundle-derived source structures and template-analysis structures, preserving complete structured evidence while keeping navigation summaries (`source_instance_overview`, `source_cluster_plan`) clearly separated from authoritative evidence. After the context contract is stable, consume `SourceCluster` read-only in agent/planner paths before touching multi-instance `RenderPlan` expression.

**Tech Stack:** Python 3.12, dataclasses, JSON Schema, pytest, python-docx, openpyxl.

---

## Constraints

- The current workspace is **not** a git worktree, so commit steps cannot run here. Replace each commit step with a short completion note in the execution log unless the repository is reattached to git first.
- Do **not** modify `/Users/paul/Coding/DataProxy`.
- `bundle` remains authoritative input. No direct raw-document parsing is added to the mapping main path in this plan.
- Preserve existing default single-`primary_record` planning behavior until the dedicated multi-instance chunks land.

## Chunk Exit Gate

Every chunk must end with a redundancy/deprecation audit before it is considered complete.

- [ ] **Audit redundant code introduced or exposed by the chunk**
  Check for duplicate builders, stale compatibility helpers, dead branches, unused imports, superseded tests, and no-longer-needed temporary adapters.
- [ ] **Delete what is no longer needed immediately**
  Do not defer obvious cleanup to a later chunk if the current chunk made the old code obsolete.
- [ ] **Re-run the chunk's focused tests after cleanup**
  Cleanup is part of the chunk, not a follow-up task.

## File Map

**New contract and builders**

- Create: `src/doctransai/mapping/full_agent_context.py`
  Purpose: Build versioned full agent context objects from `SourceModel`, `TemplateModel`, navigation summaries, and task payload.
- Create: `contracts/doctransai/full_agent_context_v1.schema.json`
  Purpose: Validate the top-level context contract used by agent preview/resolution tooling and future audits.

**Existing modules to modify**

- Modify: `src/doctransai/mapping/agent_resolver.py`
  Purpose: Replace ad hoc shared-context assembly with the new builder while preserving current behavior.
- Modify: `src/doctransai/mapping/prompts.py`
  Purpose: Render the new full context into user prompts without leaking implementation-only noise.
- Modify: `src/doctransai/prompts/agent_mapping_policy.md`
  Purpose: Instruct the model to treat navigation summaries as indexes only and full structured context as evidence.
- Modify: `src/doctransai/workflows/agent_mapping_preview.py`
  Purpose: Emit the versioned full context contract in preview payloads.
- Modify: `src/doctransai/workflows/agent_mapping_resolution.py`
  Purpose: Emit the versioned full context contract in resolution payloads.
- Modify: `src/doctransai/mapping/cluster_planner.py`
  Purpose: Enrich read-only repeat-region cluster summaries with stable ordering and coverage signals needed by future planner work.
- Modify: `src/doctransai/mapping/planner.py`
  Purpose: Add read-only cluster-aware diagnostics/task wiring only after the contract is stable; do not change default output expression yet.
- Modify: `docs/2026-05-21-doctransai-development-guide.md`
  Purpose: Keep architecture status and migration order aligned with landed code.

**Tests**

- Create: `tests/mapping/test_full_agent_context.py`
- Create: `tests/contracts/test_full_agent_context_schema.py`
- Modify: `tests/mapping/test_agent_resolver.py`
- Modify: `tests/integration/test_agent_mapping_preview.py`
- Modify: `tests/integration/test_agent_mapping_resolution.py`
- Modify: `tests/mapping/test_cluster_planning.py`
- Modify: `tests/mapping/test_planner.py`

## Chunk 1: Full Bundle Agent Context Contract

### Task 1: Define failing tests for the versioned context object

**Files:**
- Create: `tests/mapping/test_full_agent_context.py`
- Create: `tests/contracts/test_full_agent_context_schema.py`

- [ ] **Step 1: Write the failing builder test**

```python
def test_build_full_agent_context_preserves_complete_structured_source_and_template_views():
    context = build_full_agent_context(...)
    assert context["schema_version"] == "doctransai_full_agent_context_v1"
    assert "full_source_context" in context
    assert "full_template_context" in context
    assert "navigation_context" in context
    assert "task_context" in context
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `uv run pytest tests/mapping/test_full_agent_context.py -q`
Expected: FAIL because `build_full_agent_context` does not exist yet.

- [ ] **Step 3: Write the failing schema test**

```python
def test_full_agent_context_schema_accepts_minimal_complete_payload():
    payload = build_minimal_full_agent_context_payload()
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    assert errors == []
```

- [ ] **Step 4: Run the schema test to verify it fails**

Run: `uv run pytest tests/contracts/test_full_agent_context_schema.py -q`
Expected: FAIL because the schema file does not exist yet.

### Task 2: Implement the versioned context contract and builder

**Files:**
- Create: `src/doctransai/mapping/full_agent_context.py`
- Create: `contracts/doctransai/full_agent_context_v1.schema.json`
- Modify: `src/doctransai/mapping/__init__.py`

- [ ] **Step 1: Implement the top-level builder**

```python
def build_full_agent_context(
    *,
    source_model: SourceModel,
    primary_record: SourceRecord,
    template_model: TemplateModel | None,
    template_slots_by_id: dict[str, TemplateSlot],
    source_document_view: str,
    source_instance_overview: dict[str, Any],
    source_cluster_plan: dict[str, Any] | None,
    task_context: dict[str, Any],
) -> dict[str, Any]:
    ...
```

- [ ] **Step 2: Build `full_source_context` from bundle-derived structures**

Requirements:
- Include full records, images, diagnostics, and existing structured provenance-bearing views.
- Do **not** use raw document bytes or direct file parsing.
- Do **not** use semantic filtering to decide which record/table/image is “relevant”.
- Structural organization is allowed: records, images, diagnostics, document view, counts.

- [ ] **Step 3: Build `full_template_context` from template-derived structures**

Requirements:
- Include template slots, repeat regions, header regions, document view, visual pages, and template path/format metadata.
- Preserve complete template-derived structure already available in DocTransAI.

- [ ] **Step 4: Build `navigation_context`**

Requirements:
- Include `source_instance_overview`.
- Include `source_cluster_plan`.
- Add explicit metadata that these are navigation/index aids, not authoritative evidence.

- [ ] **Step 5: Build `task_context`**

Requirements:
- Include unresolved/review slot packets, resolution mode, and workflow-level context needed by the agent.
- Keep it separate from the evidence containers above.

- [ ] **Step 6: Write the JSON Schema**

Requirements:
- Top-level keys:
  `schema_version`
  `full_source_context`
  `full_template_context`
  `navigation_context`
  `task_context`
- `schema_version` must equal `doctransai_full_agent_context_v1`
- Navigation summaries must be optional or nullable where no instance/cluster is available.

- [ ] **Step 7: Run the focused tests**

Run: `uv run pytest tests/mapping/test_full_agent_context.py tests/contracts/test_full_agent_context_schema.py -q`
Expected: PASS

- [ ] **Step 8: Record completion**

Because this workspace has no `.git`, record: `Chunk 1 Task 2 completed without git commit`.

## Chunk 2: Agent Policy And Tooling Integration

### Task 3: Switch agent shared context to the versioned contract

**Files:**
- Modify: `src/doctransai/mapping/agent_resolver.py`
- Modify: `tests/mapping/test_agent_resolver.py`

- [ ] **Step 1: Write/extend failing integration tests**

Add assertions that:
- `prepare_agent_shared_context()` returns `full_agent_context`
- legacy convenience keys remain available only if deliberately retained during migration
- `full_agent_context["navigation_context"]` is present
- `full_agent_context["full_source_context"]` still exposes the complete structured source payload

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `uv run pytest tests/mapping/test_agent_resolver.py -q`
Expected: FAIL on missing `full_agent_context` assertions.

- [ ] **Step 3: Implement builder integration in `prepare_agent_shared_context()`**

Requirements:
- Use `build_full_agent_context(...)`
- Preserve existing behavior for current orchestrator callers
- Avoid duplicating large payload construction logic in `agent_resolver.py`

- [ ] **Step 4: Keep navigation as navigation**

Requirements:
- `source_instance_overview` and `source_cluster_plan` may still be exposed separately during migration,
  but agent policy must state they are indexes only.

- [ ] **Step 5: Run the focused tests**

Run: `uv run pytest tests/mapping/test_agent_resolver.py -q`
Expected: PASS

### Task 4: Update prompt policy to use full structured context

**Files:**
- Modify: `src/doctransai/prompts/agent_mapping_policy.md`
- Modify: `src/doctransai/mapping/prompts.py`
- Modify: `tests/mapping/test_agent_resolver.py`

- [ ] **Step 1: Write failing assertions for prompt wording**

Add tests that expect language equivalent to:
- full structured context is authoritative
- navigation context is not evidence by itself
- no evidence means unresolved

- [ ] **Step 2: Run the prompt-related tests to verify they fail**

Run: `uv run pytest tests/mapping/test_agent_resolver.py -q`
Expected: FAIL because prompt text does not mention the new contract rules yet.

- [ ] **Step 3: Update the prompt policy**

Requirements:
- Tell the model to use complete structured source context as evidence.
- Tell the model not to treat navigation-only summaries as proof.
- Preserve current “do not invent” and “return unresolved” rules.

- [ ] **Step 4: Update prompt rendering only if needed**

If `build_mapping_user_prompt()` or helpers need contract-aware text wrappers, make the minimal change there.

- [ ] **Step 5: Run the focused tests**

Run: `uv run pytest tests/mapping/test_agent_resolver.py -q`
Expected: PASS

### Task 5: Emit the full contract in preview/resolution tooling

**Files:**
- Modify: `src/doctransai/workflows/agent_mapping_preview.py`
- Modify: `src/doctransai/workflows/agent_mapping_resolution.py`
- Modify: `tests/integration/test_agent_mapping_preview.py`
- Modify: `tests/integration/test_agent_mapping_resolution.py`

- [ ] **Step 1: Write failing payload assertions**

Add assertions that preview and resolution payloads include:
- `full_agent_context`
- `full_agent_context["schema_version"] == "doctransai_full_agent_context_v1"`
- preserved `primary_record_id` / `source_instance_id`

- [ ] **Step 2: Run the integration tests to verify failure**

Run: `uv run pytest tests/integration/test_agent_mapping_preview.py tests/integration/test_agent_mapping_resolution.py -q`
Expected: FAIL on missing `full_agent_context`.

- [ ] **Step 3: Emit the contract in both workflows**

Requirements:
- Use the already prepared shared context instead of rebuilding anything ad hoc.
- Keep existing top-level fields for audit convenience during migration.

- [ ] **Step 4: Run the focused integration tests**

Run: `uv run pytest tests/integration/test_agent_mapping_preview.py tests/integration/test_agent_mapping_resolution.py -q`
Expected: PASS

- [ ] **Step 5: Record completion**

Because this workspace has no `.git`, record: `Chunk 2 completed without git commit`.

## Chunk 3: SourceCluster Read-Only Consumption

### Task 6: Enrich read-only cluster planning for repeat-region navigation

**Files:**
- Modify: `src/doctransai/mapping/cluster_planner.py`
- Modify: `tests/mapping/test_cluster_planning.py`

- [ ] **Step 1: Write failing tests for ordered cluster consumption**

Add tests that lock:
- cluster ordering for repeat-region candidate clusters
- instance ordering within clusters
- record/asset coverage counts per candidate cluster

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `uv run pytest tests/mapping/test_cluster_planning.py -q`
Expected: FAIL on the new ordering/coverage assertions.

- [ ] **Step 3: Implement deterministic ordering and coverage summaries**

Requirements:
- Sort instances by row index when available.
- Keep cluster summaries read-only.
- Do not alter current `RenderPlan` shape or renderer inputs.

- [ ] **Step 4: Run the focused tests**

Run: `uv run pytest tests/mapping/test_cluster_planning.py -q`
Expected: PASS

### Task 7: Feed repeat-region cluster hints into planner/agent as read-only task context

**Files:**
- Modify: `src/doctransai/mapping/full_agent_context.py`
- Modify: `src/doctransai/mapping/planner.py`
- Modify: `tests/mapping/test_planner.py`

- [ ] **Step 1: Write failing tests for read-only repeat-region hints**

Add assertions that:
- repeat-region task context includes candidate cluster ids and coverage counts
- default planner output is unchanged when no multi-instance expression is requested

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `uv run pytest tests/mapping/test_planner.py -q`
Expected: FAIL on missing repeat-region task hints.

- [ ] **Step 3: Add read-only task-context wiring**

Requirements:
- Surface repeat-region cluster hints in context/diagnostics only.
- Do **not** change current `RenderPlan.text_fills`, `image_placements`, or `record_plans` semantics.

- [ ] **Step 4: Run the focused tests**

Run: `uv run pytest tests/mapping/test_planner.py -q`
Expected: PASS

- [ ] **Step 5: Record completion**

Because this workspace has no `.git`, record: `Chunk 3 completed without git commit`.

## Chunk 4: Multi-Instance RenderPlan Design Gate

### Task 8: Prepare the schema and planner migration surface before changing behavior

**Files:**
- Modify: `docs/2026-05-21-doctransai-development-guide.md`
- Optionally create: `docs/superpowers/specs/2026-05-27-multi-instance-render-plan-design.md`

- [ ] **Step 1: Document the future expression change**

Document:
- how `RowPlan` must evolve for cluster/instance planning
- how repeat-region outputs relate to clusters
- which current tests are expected to stay green during migration

- [ ] **Step 2: Run docs-linked smoke tests only**

Run: `uv run pytest tests/mapping/test_planner.py tests/mapping/test_orchestrator.py -q`
Expected: PASS; no behavior change yet.

## Chunk 5: XLSX Region Materialization Follow-On

### Task 9: Stage the next implementation lane without executing it yet

**Files:**
- Modify: `docs/2026-05-21-doctransai-development-guide.md`
- Reference future targets:
  `src/doctransai/renderers/xlsx.py`
  `src/doctransai/templates/analyzers/p1b.py`

- [ ] **Step 1: Record the dependency order**

Document that XLSX region materialization starts **after**:
- full agent context contract is stable
- read-only cluster consumption is stable
- multi-instance RenderPlan expression is specified

- [ ] **Step 2: Record completion**

Because this workspace has no `.git`, record: `Chunk 5 staged; implementation deferred`.

## Final Verification

- [ ] Run: `uv run pytest tests/mapping/test_full_agent_context.py tests/contracts/test_full_agent_context_schema.py -q`
- [ ] Run: `uv run pytest tests/mapping/test_agent_resolver.py tests/integration/test_agent_mapping_preview.py tests/integration/test_agent_mapping_resolution.py -q`
- [ ] Run: `uv run pytest tests/mapping/test_cluster_planning.py tests/mapping/test_planner.py -q`
- [ ] Run: `uv run pytest -q`

## Execution Notes

- Keep `full_source_context` authoritative and complete, but structurally organized.
- Keep `navigation_context` available, but never let it replace evidence-bearing source structures.
- Do not modify `RenderPlan` schema until Chunk 4 explicitly begins.
- Do not add raw-document parsing or image-OCR side paths in this plan.
