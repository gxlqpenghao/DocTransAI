from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from doctransai.models.render_plan import RenderPlan


_PLACEHOLDER_PATTERN = re.compile(r"\{[^{}\r\n]+\}")
_SOURCE_RECORD_SUMMARY_PATTERN = re.compile(
    r"\bSheet\s*=\s*[^|\r\n]{1,120}\s*\|\s*Range\s*=\s*[^|\r\n]{1,120}\s*\|"
)
_UNSAFE_EMPTY_SENTENCE_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"检查发现\s*[;；]\s*[。.]",
        r"对\s*进行处罚",
        r"于\s*X",
        r"\d{4}\s*年\s*X",
        r"年\s*月\s*日\s*(?:上午|下午|中午|晚上)?[^。；;]{0,30}检查发现\s*[;；]\s*[。.]",
    ]
]


@dataclass(slots=True)
class OutputArtifactSnapshot:
    name: str
    text_fragments: list[str] = field(default_factory=list)
    applied_text_slots: set[str] = field(default_factory=set)
    applied_image_slots: set[str] = field(default_factory=set)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class OutputIssue:
    code: str
    severity: str
    message: str
    artifact_name: str | None = None
    slot_id: str | None = None
    asset_id: str | None = None
    placeholder_text: str | None = None


@dataclass(slots=True)
class OutputCheckResult:
    issues: list[OutputIssue] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.issues


def check_output(
    plan: RenderPlan,
    artifacts: list[OutputArtifactSnapshot],
    *,
    asset_base_dir: str | Path | None = None,
    include_unresolved_slots: bool = True,
    template_artifact: OutputArtifactSnapshot | None = None,
    quality_profile: str = "generic",
) -> OutputCheckResult:
    issues: list[OutputIssue] = []
    applied_text_slots = set().union(*(artifact.applied_text_slots for artifact in artifacts))
    applied_image_slots = set().union(*(artifact.applied_image_slots for artifact in artifacts))

    if _plan_expects_output_changes(plan) and not applied_text_slots and not applied_image_slots:
        issues.append(
            OutputIssue(
                code="no_op_output",
                severity="error",
                message="Render plan expected output changes, but no text or image slots were applied.",
            )
        )

    if _has_diagnostic(plan, "xlsx_no_template_regions") or _any_snapshot_has_diagnostic(
        [*artifacts, *([template_artifact] if template_artifact is not None else [])],
        "xlsx_no_template_regions",
    ):
        issues.append(
            OutputIssue(
                code="no_template_regions",
                severity="error",
                message="XLSX template analysis found no template regions; output cannot be considered a valid conversion.",
            )
        )

    if include_unresolved_slots:
        for unresolved_slot in plan.unresolved_slots:
            issues.append(
                OutputIssue(
                    code="unresolved_slot",
                    severity="warning",
                    message=unresolved_slot.message,
                    slot_id=unresolved_slot.slot_id,
                )
            )

    for artifact in artifacts:
        issues.extend(_placeholder_issues(artifact))
        issues.extend(_content_quality_issues(artifact, quality_profile=quality_profile))
        if template_artifact is not None:
            issues.extend(_template_fidelity_issues(plan, artifact, template_artifact))

    for text_fill in plan.text_fills:
        if text_fill.slot_id not in applied_text_slots:
            issues.append(
                OutputIssue(
                    code="unapplied_text_fill",
                    severity="error",
                    message=f"Text fill was not applied for slot {text_fill.slot_id}",
                    slot_id=text_fill.slot_id,
                )
            )

    for image_placement in plan.image_placements:
        if _resolve_asset_path(image_placement.source_ref, asset_base_dir, plan.source_bundle_path) is None:
            issues.append(
                OutputIssue(
                    code="missing_asset",
                    severity="error",
                    message=f"Asset is missing for slot {image_placement.slot_id}",
                    slot_id=image_placement.slot_id,
                    asset_id=image_placement.asset_id,
                )
            )
        if image_placement.slot_id not in applied_image_slots:
            issues.append(
                OutputIssue(
                    code="unapplied_image_placement",
                    severity="error",
                    message=f"Image placement was not applied for slot {image_placement.slot_id}",
                    slot_id=image_placement.slot_id,
                    asset_id=image_placement.asset_id,
                )
            )

    return OutputCheckResult(issues=issues)


def _template_fidelity_issues(
    plan: RenderPlan,
    artifact: OutputArtifactSnapshot,
    template_artifact: OutputArtifactSnapshot,
) -> list[OutputIssue]:
    issues: list[OutputIssue] = []
    format_key = _metadata_string(artifact.metadata, "format_key")

    if format_key == "docx":
        issues.extend(_docx_fidelity_issues(plan, artifact, template_artifact))
    if format_key == "xlsx":
        issues.extend(_xlsx_fidelity_issues(plan, artifact, template_artifact))

    return issues


def _docx_fidelity_issues(
    plan: RenderPlan,
    artifact: OutputArtifactSnapshot,
    template_artifact: OutputArtifactSnapshot,
) -> list[OutputIssue]:
    issues: list[OutputIssue] = []
    if not _plan_has_repeat_region_targets(plan) and artifact.metadata.get("paragraph_count") != template_artifact.metadata.get("paragraph_count"):
        issues.append(
            OutputIssue(
                code="template_structure_changed",
                severity="error",
                message="DOCX paragraph count changed after rendering.",
                artifact_name=artifact.name,
            )
        )
    if artifact.metadata.get("table_count") != template_artifact.metadata.get("table_count"):
        issues.append(
            OutputIssue(
                code="template_structure_changed",
                severity="error",
                message="DOCX table count changed after rendering.",
                artifact_name=artifact.name,
            )
        )
    template_table_cell_tokens = _metadata_list(template_artifact.metadata, "table_cell_tokens")
    output_table_cell_tokens = _metadata_list(artifact.metadata, "table_cell_tokens")
    has_table_cell_tokens = template_table_cell_tokens is not None or output_table_cell_tokens is not None
    if has_table_cell_tokens and template_table_cell_tokens != output_table_cell_tokens:
        issues.append(
            OutputIssue(
                code="template_structure_changed",
                severity="error",
                message="DOCX table cell structure changed after rendering.",
                artifact_name=artifact.name,
            )
        )

    template_styles = _metadata_dict(template_artifact.metadata, "target_styles")
    output_styles = _metadata_dict(artifact.metadata, "target_styles")
    for text_fill in plan.text_fills:
        target_key = _target_key(text_fill.target)
        if target_key in template_styles and template_styles.get(target_key) != output_styles.get(target_key):
            issues.append(
                OutputIssue(
                    code="template_style_changed",
                    severity="error",
                    message=f"DOCX style changed at {target_key}.",
                    artifact_name=artifact.name,
                    slot_id=text_fill.slot_id,
                )
            )

    image_targets = _metadata_string_set(artifact.metadata, "image_targets")
    for image_placement in plan.image_placements:
        target_key = _target_key(image_placement.target)
        if target_key not in image_targets:
            issues.append(
                OutputIssue(
                    code="image_target_mismatch",
                    severity="error",
                    message=f"DOCX image is not present at target {target_key}.",
                    artifact_name=artifact.name,
                    slot_id=image_placement.slot_id,
                    asset_id=image_placement.asset_id,
                )
            )

    return issues


def _xlsx_fidelity_issues(
    plan: RenderPlan,
    artifact: OutputArtifactSnapshot,
    template_artifact: OutputArtifactSnapshot,
) -> list[OutputIssue]:
    issues: list[OutputIssue] = []
    if artifact.metadata.get("sheet_names") != template_artifact.metadata.get("sheet_names"):
        issues.append(
            OutputIssue(
                code="template_structure_changed",
                severity="error",
                message="XLSX sheet names changed after rendering.",
                artifact_name=artifact.name,
            )
        )
    if artifact.metadata.get("merged_ranges") != template_artifact.metadata.get("merged_ranges"):
        issues.append(
            OutputIssue(
                code="template_structure_changed",
                severity="error",
                message="XLSX merged ranges changed after rendering.",
                artifact_name=artifact.name,
            )
        )
    if artifact.metadata.get("freeze_panes") != template_artifact.metadata.get("freeze_panes"):
        issues.append(
            OutputIssue(
                code="template_structure_changed",
                severity="error",
                message="XLSX freeze panes changed after rendering.",
                artifact_name=artifact.name,
            )
        )

    template_styles = _metadata_dict(template_artifact.metadata, "cell_styles")
    output_styles = _metadata_dict(artifact.metadata, "cell_styles")
    for text_fill in plan.text_fills:
        target_key = _target_key(text_fill.target)
        if target_key in template_styles and template_styles.get(target_key) != output_styles.get(target_key):
            issues.append(
                OutputIssue(
                    code="template_style_changed",
                    severity="error",
                    message=f"XLSX style changed at {target_key}.",
                    artifact_name=artifact.name,
                    slot_id=text_fill.slot_id,
                )
            )

    image_targets = _metadata_string_set(artifact.metadata, "image_targets")
    for image_placement in plan.image_placements:
        target_key = _target_key(image_placement.target)
        if target_key not in image_targets:
            issues.append(
                OutputIssue(
                    code="image_target_mismatch",
                    severity="error",
                    message=f"XLSX image is not present at target {target_key}.",
                    artifact_name=artifact.name,
                    slot_id=image_placement.slot_id,
                    asset_id=image_placement.asset_id,
                )
            )

    return issues


def _placeholder_issues(artifact: OutputArtifactSnapshot) -> list[OutputIssue]:
    issues: list[OutputIssue] = []
    for fragment in artifact.text_fragments:
        for match in _PLACEHOLDER_PATTERN.finditer(fragment):
            issues.append(
                OutputIssue(
                    code="placeholder_residue",
                    severity="error",
                    message=f"Placeholder residue found in {artifact.name}: {match.group(0)}",
                    artifact_name=artifact.name,
                    placeholder_text=match.group(0),
                )
            )
    return issues


def _content_quality_issues(artifact: OutputArtifactSnapshot, *, quality_profile: str) -> list[OutputIssue]:
    issues: list[OutputIssue] = []
    for fragment in artifact.text_fragments:
        if _SOURCE_RECORD_SUMMARY_PATTERN.search(fragment):
            issues.append(
                OutputIssue(
                    code="source_record_leakage",
                    severity="error",
                    message=f"Structured source record summary leaked into output text in {artifact.name}.",
                    artifact_name=artifact.name,
                )
            )
        if quality_profile == "zh_official":
            for pattern in _UNSAFE_EMPTY_SENTENCE_PATTERNS:
                if pattern.search(fragment):
                    issues.append(
                        OutputIssue(
                            code="unsafe_empty_sentence_skeleton",
                            severity="error",
                            message=f"Generated prose contains an empty template sentence skeleton in {artifact.name}.",
                            artifact_name=artifact.name,
                        )
                    )
    return issues


def _plan_expects_output_changes(plan: RenderPlan) -> bool:
    return bool(plan.text_fills or plan.image_placements or plan.unresolved_slots)


def _has_diagnostic(plan: RenderPlan, code: str) -> bool:
    return any(diagnostic.code == code for diagnostic in plan.diagnostics)


def _any_snapshot_has_diagnostic(artifacts: list[OutputArtifactSnapshot], code: str) -> bool:
    for artifact in artifacts:
        diagnostics = artifact.metadata.get("diagnostics")
        if not isinstance(diagnostics, list):
            continue
        for diagnostic in diagnostics:
            if isinstance(diagnostic, dict) and diagnostic.get("code") == code:
                return True
    return False


def _resolve_asset_path(
    source_ref: str | None,
    asset_base_dir: str | Path | None,
    source_bundle_path: str,
) -> Path | None:
    if not source_ref:
        return None
    path = Path(source_ref)
    if path.is_absolute():
        return path if path.exists() else None

    if asset_base_dir is not None:
        candidate = Path(asset_base_dir) / source_ref
        if candidate.exists():
            return candidate
        parsed_candidates = list((Path(asset_base_dir) / "parsed").glob(f"*/{source_ref}"))
        for parsed_candidate in parsed_candidates:
            if parsed_candidate.exists():
                return parsed_candidate

    candidate = Path(source_bundle_path).expanduser().resolve().parent / source_ref
    if candidate.exists():
        return candidate
    parsed_candidates = list(candidate.parent.joinpath("parsed").glob(f"*/{source_ref}"))
    for parsed_candidate in parsed_candidates:
        if parsed_candidate.exists():
            return parsed_candidate
    return None


def _target_key(target) -> str:
    if target.format_key == "docx":
        if target.paragraph_index is not None:
            return f"paragraph[{target.paragraph_index}]"
        if target.table_index is not None and target.row_index is not None and target.column_index is not None:
            base = f"table[{target.table_index}].cell[{target.row_index},{target.column_index}]"
            if target.cell_paragraph_index is not None:
                return f"{base}.paragraph[{target.cell_paragraph_index}]"
            return base
    if target.format_key == "xlsx":
        sheet = target.sheet_name or "<default>"
        cell = target.cell_ref or "<missing>"
        return f"{sheet}!{cell}"
    if target.format_key == "pdf":
        if target.form_field_name:
            return f"form_field:{target.form_field_name}"
        if target.page_index is not None:
            return f"page[{target.page_index}]"
    return target.target_kind


def _plan_has_repeat_region_targets(plan: RenderPlan) -> bool:
    return any(getattr(item.target, "repeat_region_id", None) is not None for item in [*plan.text_fills, *plan.image_placements])


def _metadata_dict(metadata: dict[str, object], key: str) -> dict[str, object]:
    value = metadata.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _metadata_list(metadata: dict[str, object], key: str) -> list[object] | None:
    value = metadata.get(key)
    if isinstance(value, list):
        return value
    return None


def _metadata_string(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str):
        return value
    return None


def _metadata_string_set(metadata: dict[str, object], key: str) -> set[str]:
    value = metadata.get(key)
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()
