from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from doctransai.workflows.v1_conversion import run_v1_conversion


MANIFEST_SCHEMA_VERSION = "doctransai_v1_case_manifest_v1"


@dataclass(slots=True)
class V1AuditCase:
    case_id: str
    enabled: bool
    status: str
    source_file_path: Path
    template_path: Path
    bundle_path: Path | None = None
    reference_paths: list[Path] = field(default_factory=list)
    primary_record_id: str | None = None
    source_instance_id: str | None = None
    use_mapping_agent: bool = False
    normalize_sample_template: bool = False
    decision_payload_path: Path | None = None
    notes: str | None = None


@dataclass(slots=True)
class V1CaseManifest:
    manifest_path: Path
    schema_version: str
    bundle_path: Path
    cases: list[V1AuditCase] = field(default_factory=list)


@dataclass(slots=True)
class V1BatchCaseResult:
    case_id: str
    enabled: bool
    status: str
    execution_status: str
    source_file_path: str
    template_path: str
    bundle_path: str
    primary_record_id: str | None
    source_instance_id: str | None
    use_mapping_agent: bool
    normalize_sample_template: bool
    notes: str | None
    output_path: str | None = None
    conversion_report_path: str | None = None
    provenance_report_path: str | None = None
    performance_report_path: str | None = None
    render_successful: bool | None = None
    render_clean: bool | None = None
    review_required: bool | None = None
    blocking_issue: bool | None = None
    output_clean: bool | None = None
    total_elapsed_ms: float | None = None
    applied_text_slot_count: int | None = None
    applied_image_slot_count: int | None = None
    unresolved_count: int | None = None
    diagnostic_error_count: int | None = None
    diagnostic_warning_count: int | None = None
    full_agent_context_schema_version: str | None = None
    full_source_record_count: int | None = None
    full_source_image_asset_count: int | None = None
    full_source_diagnostic_count: int | None = None
    records_truncated: bool | None = None
    diagnostics_truncated: bool | None = None
    agent_context_source_instance_id: str | None = None
    repeat_region_cluster_hints_present: bool | None = None
    repeat_region_cluster_hint_count: int | None = None
    agent_input_estimated_bytes: int | None = None
    agent_input_limit_bytes: int | None = None
    agent_input_estimated_chars: int | None = None
    agent_input_char_limit: int | None = None
    agent_input_request_body_exceeded: bool | None = None
    agent_input_length_exceeded: bool | None = None
    agent_input_within_limit: bool | None = None
    agent_input_preflight_blocked: bool | None = None
    agent_input_packaging: dict[str, Any] | None = None
    low_traceability_generated_count: int | None = None
    error_message: str | None = None


@dataclass(slots=True)
class V1BatchAuditResult:
    manifest_path: Path
    output_dir: Path
    summary: dict[str, Any]
    case_results: list[V1BatchCaseResult] = field(default_factory=list)


def load_v1_case_manifest(manifest_path: str | Path) -> V1CaseManifest:
    resolved_manifest_path = Path(manifest_path).expanduser().resolve()
    payload = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))

    schema_version = str(payload.get("schema_version", ""))
    if schema_version != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported manifest schema_version: {schema_version or '<missing>'}")

    base_dir = resolved_manifest_path.parent
    bundle_path = _resolve_manifest_path(payload["bundle_path"], base_dir)
    cases = [_case_from_payload(item, base_dir) for item in payload.get("cases", [])]

    return V1CaseManifest(
        manifest_path=resolved_manifest_path,
        schema_version=schema_version,
        bundle_path=bundle_path,
        cases=cases,
    )


def run_v1_batch_audit(
    *,
    manifest_path: str | Path,
    output_dir: str | Path | None = None,
    include_statuses: tuple[str, ...] = ("ready",),
    force_use_mapping_agent: bool | None = None,
    continue_on_error: bool = True,
) -> V1BatchAuditResult:
    manifest = load_v1_case_manifest(manifest_path)
    resolved_output_dir = _resolve_output_dir(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    case_results: list[V1BatchCaseResult] = []
    selected_statuses = list(include_statuses)

    for case in manifest.cases:
        if not case.enabled:
            case_results.append(_skipped_case_result(case, execution_status="skipped_disabled"))
            continue
        if case.status not in include_statuses:
            case_results.append(_skipped_case_result(case, execution_status="skipped_status"))
            continue

        case_dir = resolved_output_dir / "cases" / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        output_path = case_dir / case.template_path.name
        case_bundle_path = case.bundle_path or manifest.bundle_path

        try:
            workflow_result = run_v1_conversion(
                bundle_path=case_bundle_path,
                template_path=case.template_path,
                output_path=output_path,
                source_file_path=case.source_file_path,
                primary_record_id=case.primary_record_id,
                source_instance_id=case.source_instance_id,
                use_mapping_agent=case.use_mapping_agent if force_use_mapping_agent is None else force_use_mapping_agent,
                decision_payload_path=case.decision_payload_path,
                normalize_sample_template=case.normalize_sample_template,
            )
            case_results.append(_executed_case_result(case, workflow_result, bundle_path=case_bundle_path))
        except Exception as exc:  # noqa: BLE001
            case_results.append(
                V1BatchCaseResult(
                    case_id=case.case_id,
                    enabled=case.enabled,
                    status=case.status,
                    execution_status="failed",
                    source_file_path=str(case.source_file_path),
                    template_path=str(case.template_path),
                    bundle_path=str(case_bundle_path),
                    primary_record_id=case.primary_record_id,
                    source_instance_id=case.source_instance_id,
                    use_mapping_agent=case.use_mapping_agent,
                    normalize_sample_template=case.normalize_sample_template,
                    notes=case.notes,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            )
            if not continue_on_error:
                raise

    summary = _build_summary(
        manifest=manifest,
        output_dir=resolved_output_dir,
        include_statuses=selected_statuses,
        force_use_mapping_agent=force_use_mapping_agent,
        case_results=case_results,
    )
    _write_summary_files(resolved_output_dir, summary)

    return V1BatchAuditResult(
        manifest_path=manifest.manifest_path,
        output_dir=resolved_output_dir,
        summary=summary,
        case_results=case_results,
    )


def _case_from_payload(payload: dict[str, Any], base_dir: Path) -> V1AuditCase:
    return V1AuditCase(
        case_id=str(payload["case_id"]),
        enabled=bool(payload.get("enabled", True)),
        status=str(payload.get("status", "ready")),
        source_file_path=_resolve_manifest_path(payload["source_file_path"], base_dir),
        template_path=_resolve_manifest_path(payload["template_path"], base_dir),
        bundle_path=_resolve_manifest_path(payload["bundle_path"], base_dir) if payload.get("bundle_path") else None,
        reference_paths=[_resolve_manifest_path(item, base_dir) for item in payload.get("reference_paths", [])],
        primary_record_id=_optional_string(payload.get("primary_record_id")),
        source_instance_id=_optional_string(payload.get("source_instance_id")),
        use_mapping_agent=bool(payload.get("use_mapping_agent", False)),
        normalize_sample_template=bool(payload.get("normalize_sample_template", False)),
        decision_payload_path=_resolve_manifest_path(payload["decision_payload_path"], base_dir)
        if payload.get("decision_payload_path")
        else None,
        notes=_optional_string(payload.get("notes")),
    )


def _resolve_manifest_path(value: str | Path, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _resolve_output_dir(output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        return Path(output_dir).expanduser().resolve()
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return (Path.cwd() / "outputs" / "v1_audit_runs" / run_id).resolve()


def _executed_case_result(case: V1AuditCase, workflow_result, *, bundle_path: Path) -> V1BatchCaseResult:
    output_path = Path(workflow_result.render_result.output_path).expanduser().resolve()
    diagnostics = workflow_result.conversion_report.get("diagnostics", [])
    status = workflow_result.conversion_report.get("status", {})
    if not isinstance(status, dict):
        status = {}
    context_summary = workflow_result.conversion_report.get("full_agent_context_summary", {})
    if not isinstance(context_summary, dict):
        context_summary = {}
    performance_report = getattr(workflow_result, "performance_report", {}) or {}
    return V1BatchCaseResult(
        case_id=case.case_id,
        enabled=case.enabled,
        status=case.status,
        execution_status="executed",
        source_file_path=str(case.source_file_path),
        template_path=str(case.template_path),
        bundle_path=str(bundle_path),
        primary_record_id=case.primary_record_id,
        source_instance_id=case.source_instance_id,
        use_mapping_agent=case.use_mapping_agent,
        normalize_sample_template=case.normalize_sample_template,
        notes=case.notes,
        output_path=str(output_path),
        conversion_report_path=str(output_path.with_suffix(".conversion_report.json")),
        provenance_report_path=str(output_path.with_suffix(".provenance_report.json")),
        performance_report_path=str(output_path.with_suffix(".performance_report.json")),
        render_successful=workflow_result.render_result.is_successful,
        render_clean=_optional_bool(status.get("render_clean")),
        review_required=_optional_bool(status.get("review_required")),
        blocking_issue=_optional_bool(status.get("blocking_issue")),
        output_clean=workflow_result.output_check_result.is_clean,
        total_elapsed_ms=_optional_float(performance_report.get("total_elapsed_ms")),
        applied_text_slot_count=len(workflow_result.render_result.applied_text_slots),
        applied_image_slot_count=len(workflow_result.render_result.applied_image_slots),
        unresolved_count=len(workflow_result.conversion_report.get("unresolved", [])),
        diagnostic_error_count=sum(1 for item in diagnostics if item.get("severity") == "error"),
        diagnostic_warning_count=sum(1 for item in diagnostics if item.get("severity") == "warning"),
        full_agent_context_schema_version=_optional_string(context_summary.get("full_agent_context_schema_version")),
        full_source_record_count=_optional_int(context_summary.get("full_source_record_count")),
        full_source_image_asset_count=_optional_int(context_summary.get("full_source_image_asset_count")),
        full_source_diagnostic_count=_optional_int(context_summary.get("full_source_diagnostic_count")),
        records_truncated=_optional_bool(context_summary.get("records_truncated")),
        diagnostics_truncated=_optional_bool(context_summary.get("diagnostics_truncated")),
        agent_context_source_instance_id=_optional_string(context_summary.get("source_instance_id")),
        repeat_region_cluster_hints_present=_optional_bool(context_summary.get("repeat_region_cluster_hints_present")),
        repeat_region_cluster_hint_count=_optional_int(context_summary.get("repeat_region_cluster_hint_count")),
        agent_input_estimated_bytes=_optional_int(context_summary.get("agent_input_estimated_bytes")),
        agent_input_limit_bytes=_optional_int(context_summary.get("agent_input_limit_bytes")),
        agent_input_estimated_chars=_optional_int(context_summary.get("agent_input_estimated_chars")),
        agent_input_char_limit=_optional_int(context_summary.get("agent_input_char_limit")),
        agent_input_request_body_exceeded=_optional_bool(context_summary.get("agent_input_request_body_exceeded")),
        agent_input_length_exceeded=_optional_bool(context_summary.get("agent_input_length_exceeded")),
        agent_input_within_limit=_optional_bool(context_summary.get("agent_input_within_limit")),
        agent_input_preflight_blocked=_optional_bool(context_summary.get("agent_input_preflight_blocked")),
        agent_input_packaging=_optional_mapping(context_summary.get("agent_input_packaging")),
        low_traceability_generated_count=_optional_int(status.get("low_traceability_generated_count")),
    )


def _skipped_case_result(case: V1AuditCase, *, execution_status: str) -> V1BatchCaseResult:
    return V1BatchCaseResult(
        case_id=case.case_id,
        enabled=case.enabled,
        status=case.status,
        execution_status=execution_status,
        source_file_path=str(case.source_file_path),
        template_path=str(case.template_path),
        bundle_path=str(case.bundle_path) if case.bundle_path is not None else "",
        primary_record_id=case.primary_record_id,
        source_instance_id=case.source_instance_id,
        use_mapping_agent=case.use_mapping_agent,
        normalize_sample_template=case.normalize_sample_template,
        notes=case.notes,
    )


def _build_summary(
    *,
    manifest: V1CaseManifest,
    output_dir: Path,
    include_statuses: list[str],
    force_use_mapping_agent: bool | None,
    case_results: list[V1BatchCaseResult],
) -> dict[str, Any]:
    counts = {
        "total_case_count": len(case_results),
        "executed_case_count": sum(1 for item in case_results if item.execution_status == "executed"),
        "failed_case_count": sum(1 for item in case_results if item.execution_status == "failed"),
        "skipped_disabled_count": sum(1 for item in case_results if item.execution_status == "skipped_disabled"),
        "skipped_status_count": sum(1 for item in case_results if item.execution_status == "skipped_status"),
    }
    elapsed_values = [
        item.total_elapsed_ms
        for item in case_results
        if item.execution_status == "executed" and item.total_elapsed_ms is not None
    ]
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_path": str(manifest.manifest_path),
        "bundle_path": str(manifest.bundle_path),
        "output_dir": str(output_dir),
        "selected_statuses": include_statuses,
        "force_use_mapping_agent": force_use_mapping_agent,
        "counts": counts,
        "performance": {
            "measured_case_count": len(elapsed_values),
            "total_elapsed_ms": round(sum(elapsed_values), 3) if elapsed_values else 0.0,
            "average_elapsed_ms": round(sum(elapsed_values) / len(elapsed_values), 3) if elapsed_values else None,
            "max_elapsed_ms": round(max(elapsed_values), 3) if elapsed_values else None,
        },
        "agent_input_payload_governance": _build_agent_input_payload_governance(case_results),
        "cases": [asdict(item) for item in case_results],
    }


def _build_agent_input_payload_governance(case_results: list[V1BatchCaseResult]) -> dict[str, Any]:
    measured = [
        item
        for item in case_results
        if item.agent_input_estimated_bytes is not None or item.agent_input_estimated_chars is not None
    ]
    over_limit = [item.case_id for item in case_results if item.agent_input_within_limit is False]
    request_body_exceeded = [item.case_id for item in case_results if item.agent_input_request_body_exceeded is True]
    input_length_exceeded = [item.case_id for item in case_results if item.agent_input_length_exceeded is True]
    preflight_blocked = [item.case_id for item in case_results if item.agent_input_preflight_blocked is True]
    provider_request_body_failures = [
        item.case_id
        for item in case_results
        if _is_provider_request_body_limit_error(item.error_message)
    ]
    provider_input_length_failures = [
        item.case_id
        for item in case_results
        if _is_provider_input_length_limit_error(item.error_message)
    ]
    estimated_values = [
        item.agent_input_estimated_bytes
        for item in measured
        if item.agent_input_estimated_bytes is not None
    ]
    limit_values = [
        item.agent_input_limit_bytes
        for item in measured
        if item.agent_input_limit_bytes is not None
    ]
    estimated_char_values = [
        item.agent_input_estimated_chars
        for item in measured
        if item.agent_input_estimated_chars is not None
    ]
    char_limit_values = [
        item.agent_input_char_limit
        for item in measured
        if item.agent_input_char_limit is not None
    ]
    return {
        "measured_case_count": len(measured),
        "over_limit_case_count": len(over_limit),
        "request_body_exceeded_case_count": len(request_body_exceeded),
        "input_length_exceeded_case_count": len(input_length_exceeded),
        "preflight_blocked_case_count": len(preflight_blocked),
        "provider_request_body_limit_failure_count": len(provider_request_body_failures),
        "provider_input_length_limit_failure_count": len(provider_input_length_failures),
        "max_estimated_bytes": max(estimated_values) if estimated_values else None,
        "max_limit_bytes": max(limit_values) if limit_values else None,
        "max_estimated_chars": max(estimated_char_values) if estimated_char_values else None,
        "max_char_limit": max(char_limit_values) if char_limit_values else None,
        "over_limit_case_ids": over_limit,
        "request_body_exceeded_case_ids": request_body_exceeded,
        "input_length_exceeded_case_ids": input_length_exceeded,
        "preflight_blocked_case_ids": preflight_blocked,
        "provider_request_body_limit_failure_case_ids": provider_request_body_failures,
        "provider_input_length_limit_failure_case_ids": provider_input_length_failures,
    }


def _is_provider_request_body_limit_error(error_message: str | None) -> bool:
    if not error_message:
        return False
    normalized = error_message.casefold()
    return (
        "request body" in normalized
        and "max bytes" in normalized
        and ("exceeded limit" in normalized or "exceeds" in normalized)
    )


def _is_provider_input_length_limit_error(error_message: str | None) -> bool:
    if not error_message:
        return False
    normalized = error_message.casefold()
    return "range of input length" in normalized or (
        "input length" in normalized and ("260096" in normalized or "range" in normalized)
    )


def _write_summary_files(output_dir: Path, summary: dict[str, Any]) -> None:
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(_summary_markdown(summary) + "\n", encoding="utf-8")
    _write_summary_csv(output_dir / "summary.csv", summary["cases"])
    quality_payload = _quality_audit_summary(summary)
    (output_dir / "quality_audit_summary.json").write_text(
        json.dumps(quality_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "quality_audit_summary.md").write_text(
        _quality_audit_markdown(quality_payload) + "\n",
        encoding="utf-8",
    )
    blocking_payload = _blocking_issue_summary(summary)
    (output_dir / "blocking_issue_summary.json").write_text(
        json.dumps(blocking_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "blocking_issue_summary.md").write_text(
        _blocking_issue_markdown(blocking_payload) + "\n",
        encoding="utf-8",
    )
    _write_blocking_issue_csv(output_dir / "blocking_issue_summary.csv", blocking_payload["issues"])


def _quality_audit_summary(summary: dict[str, Any]) -> dict[str, Any]:
    cases = summary["cases"]
    payload_governance = summary.get("agent_input_payload_governance", {})
    return {
        "schema_version": "doctransai_v1_quality_audit_summary_v1",
        "source_summary_path": str(Path(summary["output_dir"]) / "summary.json"),
        "run_dir": summary["output_dir"],
        "agent_input_payload_governance": dict(payload_governance),
        "totals": {
            "case_count": len(cases),
            "executed_count": summary["counts"]["executed_case_count"],
            "failed_count": summary["counts"]["failed_case_count"],
            "review_required_count": _count_true(cases, "review_required"),
            "blocking_issue_count": _count_true(cases, "blocking_issue"),
            "render_successful_count": _count_true(cases, "render_successful"),
            "output_clean_count": _count_true(cases, "output_clean"),
            "unresolved_count": _sum_optional_int(cases, "unresolved_count"),
            "low_traceability_generated_count": _sum_optional_int(cases, "low_traceability_generated_count"),
            "records_truncated_count": _count_true(cases, "records_truncated"),
            "diagnostics_truncated_count": _count_true(cases, "diagnostics_truncated"),
            "agent_payload_measured_case_count": payload_governance.get("measured_case_count", 0),
            "agent_payload_over_limit_case_count": payload_governance.get("over_limit_case_count", 0),
            "agent_payload_request_body_exceeded_case_count": payload_governance.get("request_body_exceeded_case_count", 0),
            "agent_payload_input_length_exceeded_case_count": payload_governance.get("input_length_exceeded_case_count", 0),
            "agent_payload_preflight_blocked_case_count": payload_governance.get("preflight_blocked_case_count", 0),
            "agent_payload_provider_request_body_limit_failure_count": payload_governance.get(
                "provider_request_body_limit_failure_count",
                0,
            ),
            "agent_payload_provider_input_length_limit_failure_count": payload_governance.get(
                "provider_input_length_limit_failure_count",
                0,
            ),
        },
        "cases": [_quality_case_summary(item) for item in cases],
    }


def _quality_case_summary(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "execution_status": case["execution_status"],
        "output_path": case.get("output_path"),
        "error_message": case.get("error_message"),
        "unresolved_count": case.get("unresolved_count"),
        "full_source_record_count": case.get("full_source_record_count"),
        "full_source_image_asset_count": case.get("full_source_image_asset_count"),
        "records_truncated": case.get("records_truncated"),
        "diagnostics_truncated": case.get("diagnostics_truncated"),
        "repeat_region_cluster_hint_count": case.get("repeat_region_cluster_hint_count"),
        "render_successful": case.get("render_successful"),
        "render_clean": case.get("render_clean"),
        "review_required": case.get("review_required"),
        "blocking_issue": case.get("blocking_issue"),
        "output_clean": case.get("output_clean"),
        "low_traceability_generated_count": case.get("low_traceability_generated_count"),
        "full_agent_context_schema_version": case.get("full_agent_context_schema_version"),
        "agent_input_estimated_bytes": case.get("agent_input_estimated_bytes"),
        "agent_input_limit_bytes": case.get("agent_input_limit_bytes"),
        "agent_input_estimated_chars": case.get("agent_input_estimated_chars"),
        "agent_input_char_limit": case.get("agent_input_char_limit"),
        "agent_input_request_body_exceeded": case.get("agent_input_request_body_exceeded"),
        "agent_input_length_exceeded": case.get("agent_input_length_exceeded"),
        "agent_input_within_limit": case.get("agent_input_within_limit"),
        "agent_input_preflight_blocked": case.get("agent_input_preflight_blocked"),
        "agent_input_packaging": _optional_mapping(case.get("agent_input_packaging")),
        "agent_payload_provider_request_body_limit_failure": _is_provider_request_body_limit_error(case.get("error_message")),
        "agent_payload_provider_input_length_limit_failure": _is_provider_input_length_limit_error(case.get("error_message")),
    }


def _quality_audit_markdown(payload: dict[str, Any]) -> str:
    totals = payload["totals"]
    governance = payload["agent_input_payload_governance"]
    lines = [
        "# V1 Quality Audit Summary",
        "",
        f"- Run Dir: {payload['run_dir']}",
        f"- Cases: {totals['case_count']}",
        f"- Executed: {totals['executed_count']}",
        f"- Failed: {totals['failed_count']}",
        f"- Review Required: {totals['review_required_count']}",
        f"- Blocking Issue: {totals['blocking_issue_count']}",
        f"- Render Successful: {totals['render_successful_count']}",
        f"- Output Clean: {totals['output_clean_count']}",
        f"- Total Unresolved Slots: {totals['unresolved_count']}",
        f"- Low Traceability Generated Values: {totals['low_traceability_generated_count']}",
        f"- Records Truncated Cases: {totals['records_truncated_count']}",
        f"- Diagnostics Truncated Cases: {totals['diagnostics_truncated_count']}",
        f"- Agent Payload Measured Cases: {governance.get('measured_case_count')}",
        f"- Agent Payload Over Limit Cases: {governance.get('over_limit_case_count')}",
        f"- Agent Payload Request Body Exceeded Cases: {governance.get('request_body_exceeded_case_count')}",
        f"- Agent Payload Input Length Exceeded Cases: {governance.get('input_length_exceeded_case_count')}",
        f"- Agent Payload Preflight Blocked Cases: {governance.get('preflight_blocked_case_count')}",
        f"- Agent Payload Provider Request Body Limit Failures: {governance.get('provider_request_body_limit_failure_count')}",
        f"- Agent Payload Provider Input Length Limit Failures: {governance.get('provider_input_length_limit_failure_count')}",
        "",
        "| case_id | execution | review | blocking | unresolved | low_trace | records | images | truncated | hints | agent_payload | error |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload["cases"]:
        agent_payload = "provider_request_body_limit_failure" if item["agent_payload_provider_request_body_limit_failure"] else (
            "provider_input_length_limit_failure" if item["agent_payload_provider_input_length_limit_failure"] else (
            "preflight_blocked" if item.get("agent_input_preflight_blocked") is True else (
                "over_limit" if item.get("agent_input_within_limit") is False else ""
            )
            )
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["case_id"]),
                    str(item["execution_status"]),
                    str(item["review_required"]),
                    str(item["blocking_issue"]),
                    str(item["unresolved_count"]),
                    str(item["low_traceability_generated_count"]),
                    str(item["full_source_record_count"]),
                    str(item["full_source_image_asset_count"]),
                    str(bool(item["records_truncated"]) or bool(item["diagnostics_truncated"])),
                    str(item["repeat_region_cluster_hint_count"]),
                    agent_payload,
                    _markdown_cell(str(item["error_message"] or "")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _blocking_issue_summary(summary: dict[str, Any]) -> dict[str, Any]:
    issues = [
        _blocking_issue_case_summary(item)
        for item in summary["cases"]
        if item.get("blocking_issue") is True
    ]
    category_counts: Counter[str] = Counter()
    for item in issues:
        category_counts.update(item["categories"])
    return {
        "schema_version": "doctransai_v1_blocking_issue_summary_v1",
        "source_summary_path": str(Path(summary["output_dir"]) / "summary.json"),
        "run_dir": summary["output_dir"],
        "totals": {
            "blocking_issue_count": len(issues),
            "agent_payload_preflight_blocked_count": category_counts.get("agent_payload_preflight_blocked", 0),
            "provider_request_body_limit_failure_count": category_counts.get("provider_request_body_limit_failure", 0),
            "provider_input_length_limit_failure_count": category_counts.get("provider_input_length_limit_failure", 0),
            "output_check_error_count": category_counts.get("output_check_error", 0),
            "unresolved_slots_count": category_counts.get("unresolved_slots", 0),
            "context_truncated_count": category_counts.get("context_truncated", 0),
            "low_traceability_generated_count": category_counts.get("low_traceability_generated", 0),
            "category_counts": dict(sorted(category_counts.items())),
        },
        "issues": issues,
    }


def _blocking_issue_case_summary(case: dict[str, Any]) -> dict[str, Any]:
    report = _load_json_object(case.get("conversion_report_path"))
    diagnostics = report.get("diagnostics", []) if isinstance(report.get("diagnostics"), list) else []
    unresolved = report.get("unresolved", []) if isinstance(report.get("unresolved"), list) else []
    categories = _blocking_issue_categories(case, diagnostics)
    return {
        "case_id": case["case_id"],
        "execution_status": case["execution_status"],
        "source_file_path": case.get("source_file_path"),
        "template_path": case.get("template_path"),
        "bundle_path": case.get("bundle_path"),
        "output_path": case.get("output_path"),
        "conversion_report_path": case.get("conversion_report_path"),
        "provenance_report_path": case.get("provenance_report_path"),
        "primary_record_id": case.get("primary_record_id"),
        "source_instance_id": case.get("source_instance_id"),
        "use_mapping_agent": case.get("use_mapping_agent"),
        "categories": categories,
        "review_focus": _blocking_issue_review_focus(case, categories, unresolved),
        "unresolved_count": case.get("unresolved_count"),
        "diagnostic_error_count": case.get("diagnostic_error_count"),
        "diagnostic_warning_count": case.get("diagnostic_warning_count"),
        "full_source_record_count": case.get("full_source_record_count"),
        "full_source_image_asset_count": case.get("full_source_image_asset_count"),
        "records_truncated": case.get("records_truncated"),
        "diagnostics_truncated": case.get("diagnostics_truncated"),
        "agent_input_estimated_bytes": case.get("agent_input_estimated_bytes"),
        "agent_input_limit_bytes": case.get("agent_input_limit_bytes"),
        "agent_input_estimated_chars": case.get("agent_input_estimated_chars"),
        "agent_input_char_limit": case.get("agent_input_char_limit"),
        "agent_input_request_body_exceeded": case.get("agent_input_request_body_exceeded"),
        "agent_input_length_exceeded": case.get("agent_input_length_exceeded"),
        "agent_input_within_limit": case.get("agent_input_within_limit"),
        "agent_input_preflight_blocked": case.get("agent_input_preflight_blocked"),
        "agent_input_packaging": _optional_mapping(case.get("agent_input_packaging")),
        "low_traceability_generated_count": case.get("low_traceability_generated_count"),
        "top_diagnostic_codes": _diagnostic_code_counts(diagnostics),
        "unresolved_reason_codes": _unresolved_reason_counts(unresolved),
        "unresolved_fields_preview": _unresolved_fields_preview(unresolved),
        "error_message": case.get("error_message"),
    }


def _blocking_issue_categories(case: dict[str, Any], diagnostics: list[Any]) -> list[str]:
    categories: list[str] = []
    if case.get("agent_input_preflight_blocked") is True:
        categories.append("agent_payload_preflight_blocked")
    if _is_provider_request_body_limit_error(case.get("error_message")):
        categories.append("provider_request_body_limit_failure")
    if _is_provider_input_length_limit_error(case.get("error_message")):
        categories.append("provider_input_length_limit_failure")
    if _has_output_check_error(diagnostics) or _optional_int(case.get("diagnostic_error_count")):
        categories.append("output_check_error")
    if _optional_int(case.get("unresolved_count")):
        categories.append("unresolved_slots")
    if case.get("records_truncated") is True or case.get("diagnostics_truncated") is True:
        categories.append("context_truncated")
    if _optional_int(case.get("low_traceability_generated_count")):
        categories.append("low_traceability_generated")
    if case.get("render_successful") is False:
        categories.append("render_failed")
    if case.get("execution_status") == "failed":
        categories.append("execution_failed")
    return categories


def _has_output_check_error(diagnostics: list[Any]) -> bool:
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        if item.get("severity") == "error" and item.get("stage") == "output_check":
            return True
    return False


def _blocking_issue_review_focus(
    case: dict[str, Any],
    categories: list[str],
    unresolved: list[Any],
) -> list[str]:
    focus: list[str] = []
    if "agent_payload_preflight_blocked" in categories:
        focus.append("agent input exceeded provider limits; agent decision was skipped")
    if "provider_input_length_limit_failure" in categories:
        focus.append("provider rejected the agent request because input length exceeded its model limit")
    if "output_check_error" in categories:
        focus.append("output checker reported a blocking error")
    if "unresolved_slots" in categories:
        fields = ", ".join(_unresolved_fields_preview(unresolved, limit=5))
        suffix = f": {fields}" if fields else ""
        focus.append(f"{case.get('unresolved_count')} unresolved slots remain{suffix}")
    if "context_truncated" in categories:
        focus.append("full source context was truncated before reporting")
    if "low_traceability_generated" in categories:
        focus.append("generated values with low traceability require manual review")
    if "execution_failed" in categories:
        focus.append(str(case.get("error_message") or "case execution failed"))
    return focus


def _diagnostic_code_counts(diagnostics: list[Any], *, limit: int = 8) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str]] = Counter()
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "unknown")
        severity = str(item.get("severity") or "unknown")
        counter[(code, severity)] += 1
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    ordered = sorted(
        counter.items(),
        key=lambda item: (severity_rank.get(item[0][1], 9), -item[1], item[0][0]),
    )
    return [
        {"code": code, "severity": severity, "count": count}
        for (code, severity), count in ordered[:limit]
    ]


def _unresolved_reason_counts(unresolved: list[Any], *, limit: int = 8) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for item in unresolved:
        if isinstance(item, dict):
            counter[str(item.get("reason_code") or "unknown")] += 1
    return [
        {"reason_code": reason_code, "count": count}
        for reason_code, count in counter.most_common(limit)
    ]


def _unresolved_fields_preview(unresolved: list[Any], *, limit: int = 12) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for item in unresolved:
        if not isinstance(item, dict):
            continue
        field = _optional_string(item.get("canonical_key") or item.get("field") or item.get("slot_id"))
        if field is None or field in seen:
            continue
        fields.append(field)
        seen.add(field)
        if len(fields) >= limit:
            break
    return fields


def _blocking_issue_markdown(payload: dict[str, Any]) -> str:
    totals = payload["totals"]
    lines = [
        "# V1 Blocking Issue Review Table",
        "",
        f"- Run Dir: {payload['run_dir']}",
        f"- Blocking Issues: {totals['blocking_issue_count']}",
        f"- Agent Payload Preflight Blocked: {totals['agent_payload_preflight_blocked_count']}",
        f"- Provider Request Body Limit Failures: {totals['provider_request_body_limit_failure_count']}",
        f"- Provider Input Length Limit Failures: {totals['provider_input_length_limit_failure_count']}",
        f"- Output Check Errors: {totals['output_check_error_count']}",
        f"- Cases With Unresolved Slots: {totals['unresolved_slots_count']}",
        f"- Context Truncated Cases: {totals['context_truncated_count']}",
        "",
        "| case_id | categories | unresolved | errors/warnings | agent_payload | top_codes | unresolved_fields | output | report |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload["issues"]:
        agent_payload = _agent_payload_label(item)
        top_codes = ", ".join(
            f"{entry['severity']}:{entry['code']}({entry['count']})"
            for entry in item["top_diagnostic_codes"]
        )
        fields = ", ".join(item["unresolved_fields_preview"])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["case_id"]),
                    _markdown_cell(", ".join(item["categories"])),
                    str(item["unresolved_count"]),
                    f"{item['diagnostic_error_count']}/{item['diagnostic_warning_count']}",
                    _markdown_cell(agent_payload),
                    _markdown_cell(top_codes),
                    _markdown_cell(fields),
                    _markdown_file_link("output", item.get("output_path")),
                    _markdown_file_link("report", item.get("conversion_report_path")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _markdown_file_link(label: str, path_value: object) -> str:
    path = _optional_string(path_value)
    if path is None:
        return ""
    return f"[{label}](<{path.replace('>', '%3E')}>)"


def _agent_payload_label(item: dict[str, Any]) -> str:
    if item.get("agent_input_preflight_blocked") is True:
        return (
            "preflight_blocked "
            f"bytes={item.get('agent_input_estimated_bytes')}/{item.get('agent_input_limit_bytes')};"
            f"chars={item.get('agent_input_estimated_chars')}/{item.get('agent_input_char_limit')}"
        )
    if item.get("agent_input_within_limit") is False:
        return (
            "over_limit "
            f"bytes={item.get('agent_input_estimated_bytes')}/{item.get('agent_input_limit_bytes')};"
            f"chars={item.get('agent_input_estimated_chars')}/{item.get('agent_input_char_limit')}"
        )
    if item.get("agent_input_estimated_bytes") is not None:
        return (
            "measured "
            f"bytes={item.get('agent_input_estimated_bytes')}/{item.get('agent_input_limit_bytes')};"
            f"chars={item.get('agent_input_estimated_chars')}/{item.get('agent_input_char_limit')}"
        )
    return ""


def _write_blocking_issue_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
        "categories",
        "unresolved_count",
        "diagnostic_error_count",
        "diagnostic_warning_count",
        "agent_input_estimated_bytes",
        "agent_input_limit_bytes",
        "agent_input_estimated_chars",
        "agent_input_char_limit",
        "agent_input_request_body_exceeded",
        "agent_input_length_exceeded",
        "agent_input_preflight_blocked",
        "agent_input_packaging_mode",
        "top_diagnostic_codes",
        "unresolved_reason_codes",
        "unresolved_fields_preview",
        "output_path",
        "conversion_report_path",
        "provenance_report_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            packaging = _optional_mapping(row.get("agent_input_packaging"))
            writer.writerow(
                {
                    "case_id": row.get("case_id"),
                    "categories": ";".join(row.get("categories", [])),
                    "unresolved_count": row.get("unresolved_count"),
                    "diagnostic_error_count": row.get("diagnostic_error_count"),
                    "diagnostic_warning_count": row.get("diagnostic_warning_count"),
                    "agent_input_estimated_bytes": row.get("agent_input_estimated_bytes"),
                    "agent_input_limit_bytes": row.get("agent_input_limit_bytes"),
                    "agent_input_estimated_chars": row.get("agent_input_estimated_chars"),
                    "agent_input_char_limit": row.get("agent_input_char_limit"),
                    "agent_input_request_body_exceeded": row.get("agent_input_request_body_exceeded"),
                    "agent_input_length_exceeded": row.get("agent_input_length_exceeded"),
                    "agent_input_preflight_blocked": row.get("agent_input_preflight_blocked"),
                    "agent_input_packaging_mode": packaging.get("mode"),
                    "top_diagnostic_codes": ";".join(
                        f"{item['severity']}:{item['code']}={item['count']}"
                        for item in row.get("top_diagnostic_codes", [])
                    ),
                    "unresolved_reason_codes": ";".join(
                        f"{item['reason_code']}={item['count']}"
                        for item in row.get("unresolved_reason_codes", [])
                    ),
                    "unresolved_fields_preview": ";".join(row.get("unresolved_fields_preview", [])),
                    "output_path": row.get("output_path"),
                    "conversion_report_path": row.get("conversion_report_path"),
                    "provenance_report_path": row.get("provenance_report_path"),
                }
            )


def _summary_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    payload_governance = summary.get("agent_input_payload_governance", {})
    lines = [
        "# V1 Batch Audit Summary",
        "",
        f"- Manifest: {summary['manifest_path']}",
        f"- Bundle: {summary['bundle_path']}",
        f"- Output Dir: {summary['output_dir']}",
        f"- Selected Statuses: {', '.join(summary['selected_statuses'])}",
        f"- Force Agent: {summary['force_use_mapping_agent']}",
        f"- Executed: {counts['executed_case_count']}",
        f"- Failed: {counts['failed_case_count']}",
        f"- Skipped (disabled): {counts['skipped_disabled_count']}",
        f"- Skipped (status): {counts['skipped_status_count']}",
        f"- Average Elapsed: {summary['performance']['average_elapsed_ms']} ms",
        f"- Agent Payload Measured Cases: {payload_governance.get('measured_case_count')}",
        f"- Agent Payload Over Limit: {payload_governance.get('over_limit_case_count')}",
        f"- Agent Payload Request Body Exceeded: {payload_governance.get('request_body_exceeded_case_count')}",
        f"- Agent Payload Input Length Exceeded: {payload_governance.get('input_length_exceeded_case_count')}",
        f"- Agent Payload Preflight Blocked: {payload_governance.get('preflight_blocked_case_count')}",
        f"- Agent Payload Provider Request Body Limit Failures: {payload_governance.get('provider_request_body_limit_failure_count')}",
        f"- Agent Payload Provider Input Length Limit Failures: {payload_governance.get('provider_input_length_limit_failure_count')}",
        "",
        "| case_id | status | execution | elapsed_ms | render_successful | output_clean | unresolved | source_records | images | truncated | repeat_hints | agent_input_bytes | agent_input_chars | agent_input_within_limit | preflight_blocked | packaging_mode | output |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in summary["cases"]:
        packaging = _optional_mapping(item.get("agent_input_packaging"))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["case_id"]),
                    str(item["status"]),
                    str(item["execution_status"]),
                    str(item["total_elapsed_ms"]),
                    str(item["render_successful"]),
                    str(item["output_clean"]),
                    str(item["unresolved_count"]),
                    str(item["full_source_record_count"]),
                    str(item["full_source_image_asset_count"]),
                    str(bool(item["records_truncated"]) or bool(item["diagnostics_truncated"])),
                    str(item["repeat_region_cluster_hint_count"]),
                    str(item["agent_input_estimated_bytes"]),
                    str(item["agent_input_estimated_chars"]),
                    str(item["agent_input_within_limit"]),
                    str(item["agent_input_preflight_blocked"]),
                    str(packaging.get("mode")),
                    str(item["output_path"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
        "status",
        "execution_status",
        "source_file_path",
        "template_path",
        "primary_record_id",
        "source_instance_id",
        "use_mapping_agent",
        "normalize_sample_template",
        "bundle_path",
        "total_elapsed_ms",
        "render_successful",
        "output_clean",
        "applied_text_slot_count",
        "applied_image_slot_count",
        "unresolved_count",
        "diagnostic_error_count",
        "diagnostic_warning_count",
        "full_agent_context_schema_version",
        "full_source_record_count",
        "full_source_image_asset_count",
        "full_source_diagnostic_count",
        "records_truncated",
        "diagnostics_truncated",
        "agent_context_source_instance_id",
        "repeat_region_cluster_hints_present",
        "repeat_region_cluster_hint_count",
        "agent_input_estimated_bytes",
        "agent_input_limit_bytes",
        "agent_input_estimated_chars",
        "agent_input_char_limit",
        "agent_input_request_body_exceeded",
        "agent_input_length_exceeded",
        "agent_input_within_limit",
        "agent_input_preflight_blocked",
        "agent_input_packaging_mode",
        "agent_input_packaging_full_estimated_bytes",
        "agent_input_packaging_compact_estimated_bytes",
        "agent_input_packaging_selected_estimated_bytes",
        "agent_input_packaging_full_estimated_chars",
        "agent_input_packaging_compact_estimated_chars",
        "agent_input_packaging_selected_estimated_chars",
        "agent_input_packaging_char_limit",
        "agent_input_packaging_slot_packets_compacted",
        "output_path",
        "performance_report_path",
        "error_message",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            packaging = _optional_mapping(row.get("agent_input_packaging"))
            serialized = {key: row.get(key) for key in fieldnames}
            serialized.update(
                {
                    "agent_input_packaging_mode": packaging.get("mode"),
                    "agent_input_packaging_full_estimated_bytes": packaging.get("full_estimated_bytes"),
                    "agent_input_packaging_compact_estimated_bytes": packaging.get("compact_estimated_bytes"),
                    "agent_input_packaging_selected_estimated_bytes": packaging.get("selected_estimated_bytes"),
                    "agent_input_packaging_full_estimated_chars": packaging.get("full_estimated_chars"),
                    "agent_input_packaging_compact_estimated_chars": packaging.get("compact_estimated_chars"),
                    "agent_input_packaging_selected_estimated_chars": packaging.get("selected_estimated_chars"),
                    "agent_input_packaging_char_limit": packaging.get("char_limit"),
                    "agent_input_packaging_slot_packets_compacted": packaging.get("slot_packets_compacted"),
                }
            )
            writer.writerow(serialized)


def _load_json_object(path_value: object) -> dict[str, Any]:
    path_text = _optional_string(path_value)
    if path_text is None:
        return {}
    path = Path(path_text)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _count_true(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if row.get(key) is True)


def _sum_optional_int(rows: list[dict[str, Any]], key: str) -> int:
    total = 0
    for row in rows:
        value = _optional_int(row.get(key))
        if value is not None:
            total += value
    return total


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:160]


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return bool(value)


def _optional_mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
