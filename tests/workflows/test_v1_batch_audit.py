from __future__ import annotations

import json
from pathlib import Path

from docx import Document
import doctransai.workflows.v1_batch_audit as batch_module

from doctransai.workflows.v1_batch_audit import load_v1_case_manifest, run_v1_batch_audit


def test_load_v1_case_manifest_resolves_relative_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    manifest_dir = root / "V1文档审核集" / "05_样本配对_Manifest"
    source_path = root / "V1文档审核集" / "01_被转换文档_Source" / "source.xlsx"
    template_path = root / "V1文档审核集" / "02_目标模板_Template" / "template.docx"
    reference_path = root / "V1文档审核集" / "03_参考成品_Reference" / "reference.doc"
    bundle_path = root / "artifacts" / "probe" / "parsed_document_bundle.json"
    case_bundle_path = root / "artifacts" / "probe_case" / "parsed_document_bundle.json"

    for path in (source_path, template_path, reference_path, bundle_path, case_bundle_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "v1_cases.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "doctransai_v1_case_manifest_v1",
                "bundle_path": "../../artifacts/probe/parsed_document_bundle.json",
                "cases": [
                    {
                        "case_id": "case-1",
                        "enabled": True,
                        "status": "ready",
                        "source_file_path": "../01_被转换文档_Source/source.xlsx",
                        "template_path": "../02_目标模板_Template/template.docx",
                        "bundle_path": "../../artifacts/probe_case/parsed_document_bundle.json",
                        "reference_paths": ["../03_参考成品_Reference/reference.doc"],
                        "primary_record_id": "range_1",
                        "source_instance_id": "sheet_row:doc-1:Sheet0:3",
                        "use_mapping_agent": False,
                        "normalize_sample_template": True,
                        "notes": "baseline",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manifest = load_v1_case_manifest(manifest_path)

    assert manifest.schema_version == "doctransai_v1_case_manifest_v1"
    assert manifest.bundle_path == bundle_path.resolve()
    assert manifest.cases[0].source_file_path == source_path.resolve()
    assert manifest.cases[0].template_path == template_path.resolve()
    assert manifest.cases[0].bundle_path == case_bundle_path.resolve()
    assert manifest.cases[0].reference_paths == [reference_path.resolve()]
    assert manifest.cases[0].source_instance_id == "sheet_row:doc-1:Sheet0:3"
    assert manifest.cases[0].normalize_sample_template is True


def test_real_v1_manifests_include_scitech_agent_observe_case() -> None:
    manifest_paths = [
        Path("V1文档审核集/05_样本配对_Manifest/v1_cases.json"),
        Path("V1文档审核集/05_样本配对_Manifest/v1_expanded_matrix.json"),
    ]

    for manifest_path in manifest_paths:
        manifest = load_v1_case_manifest(manifest_path)
        matching_cases = [
            case
            for case in manifest.cases
            if case.case_id == "scitech_pdf_to_docx_innovation_form_agent"
        ]

        assert len(matching_cases) == 1
        case = matching_cases[0]
        assert case.enabled is True
        assert case.status == "observe"
        assert case.use_mapping_agent is True
        assert case.source_file_path.exists() is True
        assert case.template_path.exists() is True
        assert "dataproxy_fresh_probe_20260525_scitech_pdf" in str(case.bundle_path)


def test_run_v1_batch_audit_runs_ready_cases_and_writes_summaries(tmp_path: Path) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    source_path = Path(
        "V1文档审核集/01_被转换文档_Source/01_结构化台账源/安全检查台账.xlsx"
    ).resolve()
    manifest_path = tmp_path / "v1_cases.json"
    output_dir = tmp_path / "outputs" / "batch_run"

    ready_template = tmp_path / "ready-template.docx"
    ready_document = Document()
    ready_document.add_paragraph("项目：{项目名称}")
    ready_document.save(ready_template)

    observe_template = tmp_path / "observe-template.docx"
    observe_document = Document()
    observe_document.add_paragraph("隐患：{隐患描述}")
    observe_document.save(observe_template)

    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "doctransai_v1_case_manifest_v1",
                "bundle_path": str(bundle_path),
                "cases": [
                    {
                        "case_id": "ready-case",
                        "enabled": True,
                        "status": "ready",
                        "source_file_path": str(source_path),
                        "template_path": str(ready_template),
                        "reference_paths": [],
                        "primary_record_id": "range_1cd5d52e9f25",
                        "use_mapping_agent": False,
                        "notes": "baseline",
                    },
                    {
                        "case_id": "observe-case",
                        "enabled": True,
                        "status": "observe",
                        "source_file_path": str(source_path),
                        "template_path": str(observe_template),
                        "reference_paths": [],
                        "primary_record_id": "range_1cd5d52e9f25",
                        "use_mapping_agent": False,
                        "notes": "observe",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = run_v1_batch_audit(
        manifest_path=manifest_path,
        output_dir=output_dir,
        include_statuses=("ready",),
    )

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    rendered = Document(output_dir / "cases" / "ready-case" / "ready-template.docx")

    assert result.output_dir == output_dir.resolve()
    assert summary["selected_statuses"] == ["ready"]
    assert summary["counts"] == {
        "total_case_count": 2,
        "executed_case_count": 1,
        "failed_case_count": 0,
        "skipped_disabled_count": 0,
        "skipped_status_count": 1,
    }
    assert [item["execution_status"] for item in summary["cases"]] == [
        "executed",
        "skipped_status",
    ]
    assert rendered.paragraphs[0].text == "项目：西香TJ3标"
    assert (output_dir / "summary.md").exists() is True
    assert (output_dir / "summary.csv").exists() is True


def test_run_v1_batch_audit_passes_source_file_path_to_single_case_workflow(tmp_path: Path, monkeypatch) -> None:
    bundle_path = tmp_path / "bundle" / "parsed_document_bundle.json"
    source_path = tmp_path / "source.docx"
    template_path = tmp_path / "template.docx"
    manifest_path = tmp_path / "v1_cases.json"
    output_dir = tmp_path / "outputs" / "batch_run"

    for path in (bundle_path, source_path, template_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "doctransai_v1_case_manifest_v1",
                "bundle_path": str(bundle_path),
                "cases": [
                    {
                        "case_id": "ready-case",
                        "enabled": True,
                        "status": "ready",
                        "source_file_path": str(source_path),
                        "template_path": str(template_path),
                        "reference_paths": [],
                        "primary_record_id": None,
                        "use_mapping_agent": False,
                        "normalize_sample_template": True,
                        "notes": "baseline",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    observed = {}

    class _RenderResult:
        output_path = str(output_dir / "cases" / "ready-case" / "template.docx")
        applied_text_slots = []
        applied_image_slots = []
        diagnostics = []

        @property
        def is_successful(self):
            return True

    class _OutputCheckResult:
        issues = []

        @property
        def is_clean(self):
            return True

    class _WorkflowResult:
        def __init__(self):
            self.render_result = _RenderResult()
            self.output_check_result = _OutputCheckResult()
            self.conversion_report = {
                "diagnostics": [],
                "unresolved": [],
                "full_agent_context_summary": {
                    "full_agent_context_schema_version": "doctransai_full_agent_context_v1",
                    "full_source_record_count": 7,
                    "full_source_image_asset_count": 2,
                    "full_source_diagnostic_count": 1,
                    "records_truncated": False,
                    "diagnostics_truncated": False,
                    "source_instance_id": "sheet_row:doc-1:Sheet0:3",
                    "repeat_region_cluster_hints_present": True,
                    "repeat_region_cluster_hint_count": 1,
                    "agent_input_estimated_bytes": 6_500_000,
                    "agent_input_limit_bytes": 6_000_000,
                    "agent_input_estimated_chars": 270_000,
                    "agent_input_char_limit": 260_000,
                    "agent_input_request_body_exceeded": True,
                    "agent_input_length_exceeded": True,
                    "agent_input_within_limit": False,
                    "agent_input_preflight_blocked": True,
                    "agent_input_packaging": {
                        "mode": "compact_slot_packets",
                        "full_estimated_bytes": 8_000_000,
                        "compact_estimated_bytes": 6_500_000,
                        "selected_estimated_bytes": 6_500_000,
                        "limit_bytes": 6_000_000,
                        "full_estimated_chars": 300_000,
                        "compact_estimated_chars": 270_000,
                        "selected_estimated_chars": 270_000,
                        "char_limit": 260_000,
                        "request_body_exceeded": True,
                        "input_length_exceeded": True,
                        "slot_packets_compacted": True,
                        "legacy_fields_removed": ["source_document_view"],
                        "phase": "initial",
                        "within_limit": False,
                        "preflight_blocked": True,
                        "diagnostic_code": "agent_input_payload_too_large",
                    },
                },
            }
            self.performance_report = {"total_elapsed_ms": 123.456}

    def _fake_run_v1_conversion(**kwargs):
        observed.update(kwargs)
        return _WorkflowResult()

    monkeypatch.setattr(batch_module, "run_v1_conversion", _fake_run_v1_conversion)

    result = run_v1_batch_audit(
        manifest_path=manifest_path,
        output_dir=output_dir,
        include_statuses=("ready",),
    )

    assert observed["source_file_path"] == source_path.resolve()
    assert observed["normalize_sample_template"] is True
    assert result.summary["performance"]["average_elapsed_ms"] == 123.456
    assert result.case_results[0].total_elapsed_ms == 123.456
    assert result.case_results[0].performance_report_path is not None
    assert result.summary["cases"][0]["full_agent_context_schema_version"] == "doctransai_full_agent_context_v1"
    assert result.summary["cases"][0]["full_source_record_count"] == 7
    assert result.summary["cases"][0]["full_source_image_asset_count"] == 2
    assert result.summary["cases"][0]["full_source_diagnostic_count"] == 1
    assert result.summary["cases"][0]["records_truncated"] is False
    assert result.summary["cases"][0]["diagnostics_truncated"] is False
    assert result.summary["cases"][0]["agent_context_source_instance_id"] == "sheet_row:doc-1:Sheet0:3"
    assert result.summary["cases"][0]["repeat_region_cluster_hints_present"] is True
    assert result.summary["cases"][0]["repeat_region_cluster_hint_count"] == 1
    assert result.summary["cases"][0]["agent_input_estimated_bytes"] == 6_500_000
    assert result.summary["cases"][0]["agent_input_limit_bytes"] == 6_000_000
    assert result.summary["cases"][0]["agent_input_estimated_chars"] == 270_000
    assert result.summary["cases"][0]["agent_input_char_limit"] == 260_000
    assert result.summary["cases"][0]["agent_input_request_body_exceeded"] is True
    assert result.summary["cases"][0]["agent_input_length_exceeded"] is True
    assert result.summary["cases"][0]["agent_input_within_limit"] is False
    assert result.summary["cases"][0]["agent_input_preflight_blocked"] is True
    assert result.summary["cases"][0]["agent_input_packaging"]["mode"] == "compact_slot_packets"
    assert result.summary["cases"][0]["agent_input_packaging"]["legacy_fields_removed"] == ["source_document_view"]
    governance = result.summary["agent_input_payload_governance"]
    assert governance["measured_case_count"] == 1
    assert governance["over_limit_case_count"] == 1
    assert governance["request_body_exceeded_case_count"] == 1
    assert governance["input_length_exceeded_case_count"] == 1
    assert governance["preflight_blocked_case_count"] == 1
    assert governance["provider_request_body_limit_failure_count"] == 0
    assert governance["max_estimated_bytes"] == 6_500_000
    assert governance["max_estimated_chars"] == 270_000
    assert governance["over_limit_case_ids"] == ["ready-case"]
    assert governance["request_body_exceeded_case_ids"] == ["ready-case"]
    assert governance["input_length_exceeded_case_ids"] == ["ready-case"]
    assert governance["preflight_blocked_case_ids"] == ["ready-case"]
    assert "agent_input_estimated_bytes" in (output_dir / "summary.csv").read_text(encoding="utf-8")
    assert "agent_input_estimated_chars" in (output_dir / "summary.csv").read_text(encoding="utf-8")
    assert "agent_input_packaging_mode" in (output_dir / "summary.csv").read_text(encoding="utf-8")
    summary_markdown = (output_dir / "summary.md").read_text(encoding="utf-8")
    assert "agent_input_bytes" in summary_markdown
    assert "agent_input_chars" in summary_markdown
    assert "packaging_mode" in summary_markdown
    assert "Agent Payload Preflight Blocked: 1" in summary_markdown
    quality_summary = json.loads((output_dir / "quality_audit_summary.json").read_text(encoding="utf-8"))
    assert quality_summary["agent_input_payload_governance"]["preflight_blocked_case_count"] == 1
    assert quality_summary["agent_input_payload_governance"]["input_length_exceeded_case_count"] == 1
    assert quality_summary["totals"]["agent_payload_preflight_blocked_case_count"] == 1
    assert quality_summary["totals"]["agent_payload_input_length_exceeded_case_count"] == 1
    assert "Agent Payload Preflight Blocked Cases: 1" in (
        output_dir / "quality_audit_summary.md"
    ).read_text(encoding="utf-8")


def test_run_v1_batch_audit_summarizes_provider_payload_limit_failures(tmp_path: Path, monkeypatch) -> None:
    bundle_path = tmp_path / "bundle" / "parsed_document_bundle.json"
    source_path = tmp_path / "source.pdf"
    template_path = tmp_path / "template.docx"
    manifest_path = tmp_path / "v1_cases.json"
    output_dir = tmp_path / "outputs" / "batch_run"

    for path in (bundle_path, source_path, template_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "doctransai_v1_case_manifest_v1",
                "bundle_path": str(bundle_path),
                "cases": [
                    {
                        "case_id": "agent-large-payload",
                        "enabled": True,
                        "status": "observe",
                        "source_file_path": str(source_path),
                        "template_path": str(template_path),
                        "reference_paths": [],
                        "primary_record_id": None,
                        "use_mapping_agent": True,
                        "notes": "large payload",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def _fake_run_v1_conversion(**kwargs):
        raise RuntimeError("Exceeded limit on max bytes to request body : 6291456")

    monkeypatch.setattr(batch_module, "run_v1_conversion", _fake_run_v1_conversion)

    result = run_v1_batch_audit(
        manifest_path=manifest_path,
        output_dir=output_dir,
        include_statuses=("observe",),
    )

    governance = result.summary["agent_input_payload_governance"]
    assert governance["provider_request_body_limit_failure_count"] == 1
    assert governance["provider_request_body_limit_failure_case_ids"] == ["agent-large-payload"]
    assert "Agent Payload Provider Request Body Limit Failures: 1" in (
        output_dir / "summary.md"
    ).read_text(encoding="utf-8")
    quality_summary = json.loads((output_dir / "quality_audit_summary.json").read_text(encoding="utf-8"))
    assert quality_summary["agent_input_payload_governance"]["provider_request_body_limit_failure_count"] == 1
    assert quality_summary["agent_input_payload_governance"]["provider_request_body_limit_failure_case_ids"] == [
        "agent-large-payload"
    ]
    assert "Agent Payload Provider Request Body Limit Failures: 1" in (
        output_dir / "quality_audit_summary.md"
    ).read_text(encoding="utf-8")


def test_run_v1_batch_audit_summarizes_provider_input_length_limit_failures(tmp_path: Path, monkeypatch) -> None:
    bundle_path = tmp_path / "bundle" / "parsed_document_bundle.json"
    source_path = tmp_path / "source.pdf"
    template_path = tmp_path / "template.docx"
    manifest_path = tmp_path / "v1_cases.json"
    output_dir = tmp_path / "outputs" / "batch_run"

    for path in (bundle_path, source_path, template_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "doctransai_v1_case_manifest_v1",
                "bundle_path": str(bundle_path),
                "cases": [
                    {
                        "case_id": "agent-long-input",
                        "enabled": True,
                        "status": "observe",
                        "source_file_path": str(source_path),
                        "template_path": str(template_path),
                        "reference_paths": [],
                        "primary_record_id": None,
                        "use_mapping_agent": True,
                        "notes": "long input",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def _fake_run_v1_conversion(**kwargs):
        raise RuntimeError("Range of input length should be [1, 260096]")

    monkeypatch.setattr(batch_module, "run_v1_conversion", _fake_run_v1_conversion)

    result = run_v1_batch_audit(
        manifest_path=manifest_path,
        output_dir=output_dir,
        include_statuses=("observe",),
    )

    governance = result.summary["agent_input_payload_governance"]
    assert governance["provider_input_length_limit_failure_count"] == 1
    assert governance["provider_input_length_limit_failure_case_ids"] == ["agent-long-input"]
    assert "Agent Payload Provider Input Length Limit Failures: 1" in (
        output_dir / "summary.md"
    ).read_text(encoding="utf-8")
    quality_summary = json.loads((output_dir / "quality_audit_summary.json").read_text(encoding="utf-8"))
    assert quality_summary["agent_input_payload_governance"]["provider_input_length_limit_failure_count"] == 1
    assert quality_summary["totals"]["agent_payload_provider_input_length_limit_failure_count"] == 1


def test_run_v1_batch_audit_can_force_agent_usage(tmp_path: Path, monkeypatch) -> None:
    bundle_path = tmp_path / "bundle" / "parsed_document_bundle.json"
    source_path = tmp_path / "source.docx"
    template_path = tmp_path / "template.docx"
    manifest_path = tmp_path / "v1_cases.json"
    output_dir = tmp_path / "outputs" / "batch_run"

    for path in (bundle_path, source_path, template_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "doctransai_v1_case_manifest_v1",
                "bundle_path": str(bundle_path),
                "cases": [
                    {
                        "case_id": "observe-case",
                        "enabled": True,
                        "status": "observe",
                        "source_file_path": str(source_path),
                        "template_path": str(template_path),
                        "reference_paths": [],
                        "primary_record_id": None,
                        "use_mapping_agent": False,
                        "notes": "observe",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    observed = {}

    class _RenderResult:
        output_path = str(output_dir / "cases" / "observe-case" / "template.docx")
        applied_text_slots = []
        applied_image_slots = []
        diagnostics = []

        @property
        def is_successful(self):
            return True

    class _OutputCheckResult:
        issues = []

        @property
        def is_clean(self):
            return True

    class _WorkflowResult:
        def __init__(self):
            self.render_result = _RenderResult()
            self.output_check_result = _OutputCheckResult()
            self.conversion_report = {"diagnostics": [], "unresolved": []}

    def _fake_run_v1_conversion(**kwargs):
        observed.update(kwargs)
        return _WorkflowResult()

    monkeypatch.setattr(batch_module, "run_v1_conversion", _fake_run_v1_conversion)

    run_v1_batch_audit(
        manifest_path=manifest_path,
        output_dir=output_dir,
        include_statuses=("observe",),
        force_use_mapping_agent=True,
    )

    assert observed["use_mapping_agent"] is True


def test_run_v1_batch_audit_writes_blocking_issue_review_table(tmp_path: Path, monkeypatch) -> None:
    bundle_path = tmp_path / "bundle" / "parsed_document_bundle.json"
    source_path = tmp_path / "source.docx"
    template_path = tmp_path / "template.docx"
    manifest_path = tmp_path / "v1_cases.json"
    output_dir = tmp_path / "outputs" / "batch_run"

    for path in (bundle_path, source_path, template_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "doctransai_v1_case_manifest_v1",
                "bundle_path": str(bundle_path),
                "cases": [
                    {
                        "case_id": "blocking-case",
                        "enabled": True,
                        "status": "ready",
                        "source_file_path": str(source_path),
                        "template_path": str(template_path),
                        "reference_paths": [],
                        "primary_record_id": "row-1",
                        "use_mapping_agent": True,
                        "notes": "needs review",
                    },
                    {
                        "case_id": "clean-case",
                        "enabled": True,
                        "status": "ready",
                        "source_file_path": str(source_path),
                        "template_path": str(template_path),
                        "reference_paths": [],
                        "primary_record_id": "row-2",
                        "use_mapping_agent": False,
                        "notes": "clean",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    class _RenderResult:
        def __init__(self, output_path: Path, *, successful: bool):
            self.output_path = str(output_path)
            self.applied_text_slots = []
            self.applied_image_slots = []
            self.diagnostics = []
            self._successful = successful

        @property
        def is_successful(self):
            return self._successful

    class _OutputCheckResult:
        def __init__(self, *, clean: bool):
            self.issues = []
            self._clean = clean

        @property
        def is_clean(self):
            return self._clean

    class _WorkflowResult:
        def __init__(self, output_path: Path, *, blocking: bool):
            self.render_result = _RenderResult(output_path, successful=True)
            self.output_check_result = _OutputCheckResult(clean=not blocking)
            if blocking:
                self.conversion_report = {
                    "status": {
                        "render_successful": True,
                        "render_clean": False,
                        "review_required": True,
                        "blocking_issue": True,
                        "output_clean": False,
                        "low_traceability_generated_count": 1,
                    },
                    "diagnostics": [
                        {
                            "stage": "output_check",
                            "severity": "error",
                            "code": "no_op_output",
                            "message": "No fields were applied.",
                        },
                        {
                            "stage": "plan",
                            "severity": "warning",
                            "code": "missing_value",
                            "message": "No candidate was found for 负责人.",
                            "field": "负责人",
                        },
                        {
                            "stage": "agent",
                            "severity": "warning",
                            "code": "agent_input_payload_too_large",
                            "message": "Agent payload exceeded the configured provider request limit.",
                        },
                    ],
                    "unresolved": [
                        {
                            "slot_id": "slot-person",
                            "canonical_key": "负责人",
                            "reason_code": "missing_value",
                            "message": "No candidate was found for 负责人.",
                        }
                    ],
                    "full_agent_context_summary": {
                        "full_agent_context_schema_version": "doctransai_full_agent_context_v1",
                        "full_source_record_count": 12,
                        "full_source_image_asset_count": 3,
                        "full_source_diagnostic_count": 1,
                        "records_truncated": True,
                        "diagnostics_truncated": False,
                        "source_instance_id": "sheet_row:doc:Sheet1:2",
                        "repeat_region_cluster_hints_present": True,
                        "repeat_region_cluster_hint_count": 2,
                        "agent_input_estimated_bytes": 6_500_000,
                        "agent_input_limit_bytes": 6_000_000,
                        "agent_input_within_limit": False,
                        "agent_input_preflight_blocked": True,
                        "agent_input_packaging": {
                            "mode": "preflight_blocked",
                            "full_estimated_bytes": 8_000_000,
                            "compact_estimated_bytes": 6_500_000,
                            "selected_estimated_bytes": 6_500_000,
                            "limit_bytes": 6_000_000,
                            "slot_packets_compacted": True,
                            "legacy_fields_removed": ["source_document_view"],
                            "phase": "initial",
                            "within_limit": False,
                            "preflight_blocked": True,
                            "diagnostic_code": "agent_input_payload_too_large",
                        },
                    },
                }
            else:
                self.conversion_report = {
                    "status": {
                        "render_successful": True,
                        "render_clean": True,
                        "review_required": False,
                        "blocking_issue": False,
                        "output_clean": True,
                        "low_traceability_generated_count": 0,
                    },
                    "diagnostics": [],
                    "unresolved": [],
                    "full_agent_context_summary": {
                        "full_agent_context_schema_version": "doctransai_full_agent_context_v1",
                        "full_source_record_count": 2,
                        "full_source_image_asset_count": 0,
                        "full_source_diagnostic_count": 0,
                        "records_truncated": False,
                        "diagnostics_truncated": False,
                        "repeat_region_cluster_hints_present": False,
                        "repeat_region_cluster_hint_count": 0,
                    },
                }
            self.performance_report = {"total_elapsed_ms": 10.0}
            output_path.with_suffix(".conversion_report.json").write_text(
                json.dumps(self.conversion_report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    def _fake_run_v1_conversion(**kwargs):
        output_path = Path(kwargs["output_path"])
        return _WorkflowResult(output_path, blocking=output_path.parent.name == "blocking-case")

    monkeypatch.setattr(batch_module, "run_v1_conversion", _fake_run_v1_conversion)

    run_v1_batch_audit(
        manifest_path=manifest_path,
        output_dir=output_dir,
        include_statuses=("ready",),
    )

    payload = json.loads((output_dir / "blocking_issue_summary.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "doctransai_v1_blocking_issue_summary_v1"
    assert payload["totals"]["blocking_issue_count"] == 1
    assert payload["totals"]["agent_payload_preflight_blocked_count"] == 1
    assert payload["issues"][0]["case_id"] == "blocking-case"
    assert payload["issues"][0]["categories"] == [
        "agent_payload_preflight_blocked",
        "output_check_error",
        "unresolved_slots",
        "context_truncated",
        "low_traceability_generated",
    ]
    assert payload["issues"][0]["top_diagnostic_codes"][0] == {
        "code": "no_op_output",
        "severity": "error",
        "count": 1,
    }
    assert payload["issues"][0]["unresolved_reason_codes"] == [{"reason_code": "missing_value", "count": 1}]
    assert payload["issues"][0]["unresolved_fields_preview"] == ["负责人"]
    assert payload["issues"][0]["agent_input_packaging"]["mode"] == "preflight_blocked"
    markdown = (output_dir / "blocking_issue_summary.md").read_text(encoding="utf-8")
    assert "blocking-case" in markdown
    assert "agent_payload_preflight_blocked" in markdown
    assert "no_op_output" in markdown
    assert "负责人" in markdown
    assert "blocking_issue_summary.csv" in {path.name for path in output_dir.iterdir()}
