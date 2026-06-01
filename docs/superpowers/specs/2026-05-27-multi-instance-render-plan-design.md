# Multi-Instance RenderPlan Design Gate

> Status: design gate only. This document does not authorize a schema or renderer behavior change.

## Purpose

DocTransAI currently has a stable V1 path centered on one selected `primary_record`. That path must remain valid. The next capability step is to support templates that contain a main information area, repeated detail rows, image groups, and signatures/approval zones in one output. This requires a future `RenderPlan` expression that can represent source instances and source clusters without letting agent hints become hidden planning decisions.

This design gate defines the migration surface before any schema change is implemented.

## Current Baseline

Current `doctransai_render_plan_v1` uses:

- `RenderPlan.record_plans: list[RowPlan]`
- `RowPlan.record_id`
- `RowPlan.repeat_region_id`
- `RowPlan.slot_ids`
- `TextFill` / `ImagePlacement` with concrete `target`
- optional repeat execution through `TargetRef.repeat_region_id` and `TargetRef.instance_index`

This works for:

- single source record to one template/form
- current DOCX repeat media expansion where concrete fills/placements already contain `slot@0`, `slot@1`, ...
- auditable renderer execution because renderers only consume `RenderPlan`

It does not yet express:

- one template bound to multiple source instances
- a repeat region intentionally bound to one `SourceCluster`
- a main section using one source instance while a detail section uses a cluster
- row-band or sheet-region materialization for XLSX

## Non-Negotiable Constraints

- DataProxy bundle remains the upstream source. No raw-document agent path is introduced here.
- `full_agent_context` and `source_cluster_plan` are planning inputs, not output instructions.
- Renderers must continue to execute `RenderPlan`; renderers must not read `SourceCluster`, `SourceInstanceIndex`, or DataProxy bundle directly.
- V1 single-record behavior must remain green throughout migration.
- Provenance must stay attached to each concrete `TextFill` / `ImagePlacement`.
- Repeat-region hints are not enough to render. A future schema must explicitly state which cluster/instance is selected.

## Future Expression Shape

The schema-changing step should use a new schema version, expected to be `doctransai_render_plan_v2`, rather than silently expanding v1 with required fields.

`RowPlan` should evolve from a row-only summary into a planning unit while remaining able to represent the legacy case.

Proposed future fields:

```python
@dataclass(slots=True)
class RowPlan:
    record_id: str | None
    repeat_region_id: str | None = None
    slot_ids: list[str] = field(default_factory=list)

    plan_unit_id: str | None = None
    plan_unit_kind: str = "single_record"
    source_instance_id: str | None = None
    source_cluster_id: str | None = None
    instance_index: int | None = None
    parent_plan_unit_id: str | None = None
    child_plan_unit_ids: list[str] = field(default_factory=list)
```

Allowed `plan_unit_kind` values should start conservatively:

- `single_record`: V1-compatible unit. `record_id` is present. No multi-instance semantics.
- `source_instance`: one selected `SourceInstance`. Used when source_instance_id is the stable source scope.
- `source_cluster`: one selected `SourceCluster`. Used as the parent of repeat-region instance units.
- `repeat_region_instance`: one materialized instance inside a repeat region. Has `source_instance_id`, `source_cluster_id`, `repeat_region_id`, and `instance_index`.

Important compatibility rule:

- Existing v1 payloads without the new fields must continue to load as `single_record`.
- V2 payloads may include the new fields, but renderers should still operate from concrete `TextFill` / `ImagePlacement` targets until renderer-specific materialization support is added.

## Repeat Region To Cluster Relationship

For a future repeat region output, the plan must state both the selected cluster and the ordered instances.

Minimum future structure:

```json
{
  "plan_unit_kind": "source_cluster",
  "source_cluster_id": "sheet:doc-1:Sheet0",
  "repeat_region_id": "region-issues",
  "child_plan_unit_ids": [
    "region-issues#0",
    "region-issues#1"
  ]
}
```

Each child unit then binds one materialized repeat item:

```json
{
  "plan_unit_id": "region-issues#0",
  "plan_unit_kind": "repeat_region_instance",
  "source_cluster_id": "sheet:doc-1:Sheet0",
  "source_instance_id": "sheet_row:doc-1:Sheet0:3",
  "repeat_region_id": "region-issues",
  "instance_index": 0,
  "slot_ids": ["slot-photo@0", "slot-desc@0"]
}
```

This prevents three failure modes:

- agent or renderer guessing how many repeat items to create
- cluster hints being mistaken for selected output instructions
- generated output losing the source instance relationship after rendering

## Planner Migration Surface

Migration should happen in four narrow steps:

1. Keep v1 default behavior unchanged.
2. Add optional in-memory planning units behind a feature flag or explicit schema version, without emitting them in v1.
3. Add v2 serialization and loader compatibility tests.
4. Only after v2 planning units are stable, let renderer-specific materialization consume v2 plan units.

The first planner consumer should be DOCX repeat region planning because it already has `repeat_region_id` and `instance_index` concepts. XLSX region materialization should wait until the v2 plan can express row-band cloning targets.

## Renderer Boundary

Renderer inputs should remain explicit:

- DOCX renderer consumes concrete paragraph/table/image targets.
- XLSX renderer should eventually consume region materialization instructions, but only after `RenderPlan` v2 can represent them.
- PDF remains AcroForm-oriented until a separate ordinary-PDF template strategy is designed.

Renderer must not:

- infer cluster membership
- decide source instance order
- choose image count
- fetch DataProxy bundle context

## Tests That Must Stay Green During Migration

These tests protect current V1 behavior:

- `uv run pytest tests/mapping/test_planner.py tests/mapping/test_orchestrator.py -q`
- `uv run pytest tests/models/test_render_plan.py tests/contracts/test_render_plan_schema.py -q`
- `uv run pytest tests/renderers/test_docx_renderer.py tests/renderers/test_xlsx_renderer.py -q`
- `uv run pytest tests/integration/test_v1_conversion_workflow.py -q`

The first v2 implementation chunk should add tests for:

- v1 payload loads as `single_record`
- v2 `source_cluster` parent with ordered `repeat_region_instance` children round-trips
- concrete fills still carry provenance after multi-instance planning
- renderer ignores v2-only planning metadata unless explicitly enabled

## Explicitly Deferred

- No schema edit in this design gate.
- No renderer change in this design gate.
- No XLSX row cloning in this design gate.
- No raw-doc agent fallback in this design gate.
