from __future__ import annotations

import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "attribute_unresolved_targets.py"
_SPEC = importlib.util.spec_from_file_location("attribute_unresolved_targets", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

_row = _MODULE._row
_summary = _MODULE._summary


def _case() -> dict:
    return {
        "case_id": "case-1",
        "output_path": "/tmp/out.docx",
        "report_path": "/tmp/out.agentic_report.json",
        "preview_dir": "/tmp/previews",
    }


def test_source_missing_person_is_not_actionable_issue() -> None:
    row = _row(
        _case(),
        {
            "target_id": "slot-person",
            "label": "检查人",
            "expected_content_type": "text",
            "decision_type": "unresolved",
            "decision_status": "accepted",
            "render_status": "unresolved",
            "reason": "Source record has no field labeled 检查人 or equivalent inspector name.",
            "diagnostics": [],
        },
    )

    assert row["category"] == "source_absent_person_role"
    assert row["acceptance_class"] == "source_missing_or_not_supported"
    assert row["actionable_issue"] is False


def test_image_reference_gap_is_actionable_issue() -> None:
    row = _row(
        _case(),
        {
            "target_id": "slot-photo",
            "label": "隐患照片",
            "expected_content_type": "image",
            "decision_type": "image_placement",
            "decision_status": "rejected",
            "render_status": "unresolved",
            "reason": "Agent selected a source image.",
            "diagnostics": ["source_ref_not_found"],
        },
    )

    assert row["category"] == "image_asset_reference_gap"
    assert row["acceptance_class"] == "actionable_channel_gap"
    assert row["actionable_issue"] is True


def test_not_applicable_target_is_not_actionable_issue() -> None:
    row = _row(
        _case(),
        {
            "target_id": "visual-target-other",
            "label": "其他（注明：__________）",
            "expected_content_type": "text",
            "decision_type": "not_applicable",
            "decision_status": "accepted",
            "render_status": "not_applicable",
            "reason": "Only relevant when 其他 is selected.",
            "diagnostics": [],
        },
    )

    assert row["category"] == "conditional_not_required"
    assert row["acceptance_class"] == "not_applicable"
    assert row["actionable_issue"] is False


def test_summary_counts_actionable_issues_separately() -> None:
    rows = [
        {"case_id": "case-1", "category": "source_absent_person_role", "acceptance_class": "source_missing_or_not_supported", "actionable_issue": False, "recommended_action": "keep unresolved"},
        {"case_id": "case-1", "category": "image_asset_reference_gap", "acceptance_class": "actionable_channel_gap", "actionable_issue": True, "recommended_action": "fix channel"},
    ]

    summary = _summary(rows, matrix_dir=Path("/tmp/matrix"))

    assert summary["counts"]["total_unresolved_or_rejected"] == 2
    assert summary["counts"]["actionable_issue_count"] == 1
    assert summary["counts"]["acceptance_class_counts"] == {
        "source_missing_or_not_supported": 1,
        "actionable_channel_gap": 1,
    }
