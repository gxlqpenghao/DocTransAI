from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute unresolved/rejected targets in agentic physical acceptance outputs.")
    parser.add_argument(
        "--matrix-dir",
        type=Path,
        default=Path("outputs/agentic_skeleton/physical_acceptance_matrix_current"),
    )
    args = parser.parse_args()

    matrix_dir = args.matrix_dir.expanduser().resolve()
    summary_path = matrix_dir / "physical_acceptance_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))

    rows = _build_rows(payload.get("cases", []))
    summary = _summary(rows, matrix_dir=matrix_dir)
    _write_outputs(matrix_dir, summary, rows)
    print(json.dumps(summary["counts"], ensure_ascii=False), flush=True)


def _build_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        report_path = Path(case["report_path"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for item in report.get("target_ledger", []):
            if item.get("render_status") == "applied":
                continue
            row = _row(case, item)
            rows.append(row)
    return rows


def _row(case: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    reason = str(item.get("reason") or "")
    diagnostics = item.get("diagnostics") or []
    diagnostic_codes = [
        str(entry.get("code")) if isinstance(entry, dict) else str(entry)
        for entry in diagnostics
        if entry
    ]
    category, action = _classify(
        label=str(item.get("label") or ""),
        target_id=str(item.get("target_id") or ""),
        expected_content_type=str(item.get("expected_content_type") or ""),
        decision_type=str(item.get("decision_type") or ""),
        decision_status=str(item.get("decision_status") or ""),
        render_status=str(item.get("render_status") or ""),
        reason=reason,
        diagnostic_codes=diagnostic_codes,
    )
    acceptance_class = _acceptance_class(category)
    return {
        "case_id": case["case_id"],
        "target_id": item.get("target_id"),
        "label": item.get("label"),
        "expected_content_type": item.get("expected_content_type"),
        "decision_type": item.get("decision_type"),
        "decision_status": item.get("decision_status"),
        "render_status": item.get("render_status"),
        "value_preview": item.get("value_preview"),
        "source_refs": item.get("source_refs") or [],
        "diagnostic_codes": diagnostic_codes,
        "category": category,
        "acceptance_class": acceptance_class,
        "actionable_issue": acceptance_class in {"actionable_channel_gap", "needs_manual_review"},
        "recommended_action": action,
        "reason": reason,
        "output_path": case.get("output_path"),
        "report_path": case.get("report_path"),
        "preview_dir": case.get("preview_dir"),
    }


def _classify(
    *,
    label: str,
    target_id: str,
    expected_content_type: str,
    decision_type: str,
    decision_status: str,
    render_status: str,
    reason: str,
    diagnostic_codes: list[str],
) -> tuple[str, str]:
    text = " ".join(
        [label, target_id, expected_content_type, decision_type, decision_status, render_status, reason, " ".join(diagnostic_codes)]
    ).lower()
    original = " ".join([label, target_id, reason, " ".join(diagnostic_codes)])

    if decision_type == "not_applicable" or render_status == "not_applicable":
        return "conditional_not_required", "条件项不适用，按正确未填处理；不算通道失败。"
    if "source_ref_not_found" in diagnostic_codes:
        return "image_asset_reference_gap", "修现有图片资产/asset_ref 映射通道；源里有可见图片或模型选择了图片，但 renderer 无法用该引用取到文件。"
    if expected_content_type == "image" and ("visual page renders show photos" in text or "image cells" in text):
        return "image_asset_extraction_gap", "源页面/表格视觉上有图片，但 bundle 没有可用 image_assets；这是图片资产提取/传递通道缺口。"
    if expected_content_type == "image" and ("no image assets" in text or "image_assets" in text or "没有图片" in original or "无图片" in original):
        return "source_absent_image_or_unconfirmed_asset_gap", "当前证据包无可用图片；若人工确认源页面有图，则归图片资产通道缺口，否则保持 unresolved。"
    if "target_ref_not_found" in diagnostic_codes:
        return "visual_target_reference_gap", "视觉目标已被发现但没有进入统一目标引用层；修 target_ref/object_index 通道。"
    if "text_value_not_supported_by_source_ref" in diagnostic_codes:
        return "source_concept_mismatch", "源证据不支持该值，按源缺或语义不相关处理；不应强行填。"
    if "decision_reason_contradicts_fill" in diagnostic_codes:
        return "semantic_mismatch_rejected", "当前 validator 拦截正确；若业务允许该映射，应先改 prompt/证据选择，不直接放宽验证。"

    if "其他" in original and ("conditional" in text or "智能建造" in original):
        return "conditional_not_required", "条件项，主选项已填写时无需填；报告中应标记为 not_applicable 优于 unresolved。"
    if any(token in original for token in ["编号", "表格编号", "document number", "form number", "synthesize", "合成"]):
        return "source_absent_document_metadata", "源缺文档/表格编号；不要合成，除非以后引入编号生成规则并显式启用。"
    if any(token in original for token in ["盖章", "公章", "签字", "接收人", "seal", "stamp asset", "signature"]):
        return "manual_signature_or_seal", "人工项，不应自动填；保留空白或在报告中标为需人工处理。"
    if any(token in original for token in ["手机号", "电话", "phone"]):
        return "source_absent_contact", "源缺联系方式；保持 unresolved。"
    if any(token in original for token in ["检查部门", "项目安全管理部", "department", "部门"]):
        return "source_absent_department_context", "源缺模板语境下的检查/管理部门；不能用责任单位或参与部门强行代替。"
    if any(token in original for token in ["罚款", "处罚金额", "大写", "penalty amount", "fine amount"]):
        return "source_absent_penalty_fields", "源不是处罚单或未含罚款金额；保持 unresolved。"
    if any(token in original for token in ["隐患等级", "隐患类型", "hazard level", "hazard type", "severity grade"]):
        return "source_absent_hazard_classification", "源只有隐患描述或检查项，缺隐患类型/等级分类；保持 unresolved。"
    if any(token in original for token in ["检查部位", "安全责任区域", "single inspection location", "责任区域", "multiple areas"]):
        return "source_ambiguous_location_or_area", "源覆盖多个部位/区域，模板要求单一位置或责任区域；不应猜测。"
    if "责任单位" in original and any(token in original for token in ["penalty", "处罚", "specific", "not a penalty"]):
        return "source_absent_responsible_unit_context", "源有组织名但缺处罚/整改语境下的责任单位；保持 unresolved。"
    if any(token in original for token in ["复查", "review", "整改完成", "整改时间", "整改描述", "整改照片"]):
        return "source_absent_followup_or_rectification_result", "源只描述检查/整改要求，缺整改完成或复查结果；保持 unresolved。"
    if any(token in original for token in ["检查人", "责任人", "负责人", "整改监督人", "人员姓名", "person", "name", "names", "supervisor"]):
        return "source_absent_person_role", "源缺具体人员或角色不等价；保持 unresolved。"
    if any(token in original for token in ["期限", "duration", "deadline", "日期", "时间", "年月日", "date"]):
        return "source_absent_or_mismatched_date", "源缺对应业务日期，或只有期限/季度/检查日，不能替代签发/接收/完成日期。"
    if any(token in original for token in ["隐患描述", "整改要求", "hazard description", "rectification requirements"]):
        return "source_concept_mismatch", "源内容与模板目标业务语义不一致，按源缺处理；不应强行填。"
    if "empty_text_fill_converted_to_unresolved" in diagnostic_codes:
        return "source_absent_empty_field", "模型返回空值且已被保护性转 unresolved；源字段缺失。"
    if any(token in original for token in ["no explicit", "no source", "no field", "not contain", "未包含", "没有", "无", "缺"]):
        return "source_absent_generic", "源证据不足；保持 unresolved。"
    return "needs_manual_review", "归因规则未覆盖；需人工看 report reason 和预览页。"


def _acceptance_class(category: str) -> str:
    if category == "conditional_not_required":
        return "not_applicable"
    if category == "manual_signature_or_seal":
        return "manual_required"
    if category in {
        "image_asset_reference_gap",
        "image_asset_extraction_gap",
        "visual_target_reference_gap",
    }:
        return "actionable_channel_gap"
    if category.startswith("source_absent_") or category in {
        "source_concept_mismatch",
        "source_ambiguous_location_or_area",
        "semantic_mismatch_rejected",
    }:
        return "source_missing_or_not_supported"
    return "needs_manual_review"


def _summary(rows: list[dict[str, Any]], *, matrix_dir: Path) -> dict[str, Any]:
    category_counts = Counter(row["category"] for row in rows)
    acceptance_class_counts = Counter(row["acceptance_class"] for row in rows)
    case_counts = Counter(row["case_id"] for row in rows)
    action_counts = Counter(row["recommended_action"] for row in rows)
    return {
        "schema_name": "agentic_unresolved_attribution",
        "matrix_dir": str(matrix_dir),
        "counts": {
            "total_unresolved_or_rejected": len(rows),
            "actionable_issue_count": sum(1 for row in rows if row.get("actionable_issue")),
            "category_counts": dict(category_counts.most_common()),
            "acceptance_class_counts": dict(acceptance_class_counts.most_common()),
            "case_counts": dict(case_counts.most_common()),
            "recommended_action_counts": dict(action_counts.most_common()),
        },
    }


def _write_outputs(matrix_dir: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    json_path = matrix_dir / "unresolved_attribution.json"
    csv_path = matrix_dir / "unresolved_attribution.csv"
    md_path = matrix_dir / "unresolved_attribution.md"

    json_path.write_text(
        json.dumps({"summary": summary, "items": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fields = [
        "case_id",
        "target_id",
        "label",
        "expected_content_type",
        "decision_type",
        "decision_status",
        "render_status",
        "category",
        "acceptance_class",
        "actionable_issue",
        "recommended_action",
        "diagnostic_codes",
        "value_preview",
        "reason",
        "output_path",
        "preview_dir",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            csv_row = {field: row.get(field) for field in fields}
            csv_row["diagnostic_codes"] = ";".join(row.get("diagnostic_codes") or [])
            writer.writerow(csv_row)

    md_path.write_text(_markdown(summary, rows), encoding="utf-8")


def _markdown(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Unresolved Attribution",
        "",
        f"- Matrix dir: `{summary['matrix_dir']}`",
        f"- Total unresolved/rejected: `{summary['counts']['total_unresolved_or_rejected']}`",
        f"- Actionable issues: `{summary['counts']['actionable_issue_count']}`",
        "",
        "## Acceptance Class Counts",
        "",
    ]
    for acceptance_class, count in summary["counts"]["acceptance_class_counts"].items():
        lines.append(f"- `{acceptance_class}`: {count}")
    lines.extend([
        "",
        "## Category Counts",
        "",
    ])
    for category, count in summary["counts"]["category_counts"].items():
        lines.append(f"- `{category}`: {count}")
    lines.extend(["", "## Case Counts", ""])
    for case_id, count in summary["counts"]["case_counts"].items():
        lines.append(f"- `{case_id}`: {count}")
    lines.extend(
        [
            "",
            "## Items",
            "",
            "| case | target | label | class | category | action | reason |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        reason = _compact(row["reason"], 130)
        action = _compact(row["recommended_action"], 80)
        lines.append(
            "| {case} | `{target}` | {label} | `{klass}` | `{category}` | {action} | {reason} |".format(
                case=row["case_id"],
                target=row["target_id"],
                label=_escape(row.get("label") or ""),
                klass=row["acceptance_class"],
                category=row["category"],
                action=_escape(action),
                reason=_escape(reason),
            )
        )
    return "\n".join(lines) + "\n"


def _compact(value: str, limit: int) -> str:
    value = " ".join(str(value).split())
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _escape(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
