from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from docx import Document
from openpyxl import load_workbook

from doctransai.workflows.agentic_conversion import run_agentic_conversion


TEXT_PLACEHOLDER_RE = re.compile(r"\{[^{}\n]{1,80}\}")
BLANK_MARKER_RE = re.compile(r"_{4,}")
DRAWING_EXT_RE = re.compile(r'<ext cx="(?P<cx>\d+)" cy="(?P<cy>\d+)"')
EMU_PER_PIXEL = 9525
OVERSIZED_XLSX_IMAGE_PX = 1000


def main() -> None:
    parser = argparse.ArgumentParser(description="Run agentic physical artifact acceptance matrix.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("V1文档审核集/05_样本配对_Manifest/v1_expanded_matrix.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/agentic_skeleton/physical_acceptance_matrix_current"),
    )
    parser.add_argument("--statuses", nargs="+", default=["ready", "observe"])
    parser.add_argument("--reuse-existing-artifacts", action="store_true")
    args = parser.parse_args()

    manifest_path = args.manifest.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = _load_cases(manifest_path, statuses=set(args.statuses))
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['case_id']} start", flush=True)
        result = _run_case(case, output_dir=output_dir, reuse_existing_artifacts=args.reuse_existing_artifacts)
        results.append(result)
        print(
            f"[{index}/{len(cases)}] {case['case_id']} {result['artifact_status']} "
            f"pages={result.get('pdf_page_count')} issues={len(result['channel_issues'])}",
            flush=True,
        )

    summary = _build_summary(manifest_path=manifest_path, output_dir=output_dir, results=results)
    _write_outputs(output_dir, summary, results)
    print(json.dumps(summary["counts"], ensure_ascii=False), flush=True)


def _load_cases(manifest_path: Path, *, statuses: set[str]) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_dir = manifest_path.parent
    manifest_bundle = _resolve_path(payload["bundle_path"], base_dir)
    cases: list[dict[str, Any]] = []
    for item in payload.get("cases", []):
        if not item.get("enabled", True):
            continue
        if str(item.get("status", "ready")) not in statuses:
            continue
        cases.append(
            {
                "case_id": str(item["case_id"]),
                "status": str(item.get("status", "ready")),
                "source_file_path": _resolve_path(item["source_file_path"], base_dir),
                "template_path": _resolve_path(item["template_path"], base_dir),
                "bundle_path": _resolve_path(item["bundle_path"], base_dir) if item.get("bundle_path") else manifest_bundle,
                "source_record_id": item.get("primary_record_id"),
            }
        )
    return cases


def _run_case(case: dict[str, Any], *, output_dir: Path, reuse_existing_artifacts: bool) -> dict[str, Any]:
    case_id = str(case["case_id"])
    artifact_dir = output_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_path = artifact_dir / f"{case_id}{Path(case['template_path']).suffix}"
    try:
        report_path = output_path.with_suffix(".agentic_report.json")
        if reuse_existing_artifacts and output_path.exists() and report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
        else:
            conversion = run_agentic_conversion(
                bundle_path=case["bundle_path"],
                template_path=case["template_path"],
                output_path=output_path,
                source_file_path=case["source_file_path"],
                source_record_id=case.get("source_record_id"),
            )
            report = conversion.audit_report
        inspection = _inspect_artifact(output_path, report, output_dir=output_dir, case_id=case_id)
        return {
            "case_id": case_id,
            "status": case["status"],
            "execution_status": "ok",
            "source_file_path": str(case["source_file_path"]),
            "template_path": str(case["template_path"]),
            "bundle_path": str(case["bundle_path"]),
            "output_path": str(output_path),
            "report_path": str(report_path),
            **inspection,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "case_id": case_id,
            "status": case["status"],
            "execution_status": "failed",
            "source_file_path": str(case["source_file_path"]),
            "template_path": str(case["template_path"]),
            "bundle_path": str(case["bundle_path"]),
            "output_path": str(output_path),
            "artifact_status": "failed",
            "channel_issues": [f"conversion_failed:{type(exc).__name__}: {exc}"],
            "review_flags": [],
        }


def _inspect_artifact(output_path: Path, report: dict[str, Any], *, output_dir: Path, case_id: str) -> dict[str, Any]:
    if output_path.suffix.lower() == ".xlsx":
        artifact = _inspect_xlsx(output_path)
    else:
        artifact = _inspect_docx(output_path)

    applied_text_slots = set(report.get("applied_text_slots") or [])
    applied_image_slots = set(report.get("applied_image_slots") or [])
    text_values = _accepted_text_values(report)
    missing_text_slots = _missing_applied_texts(text_values, applied_text_slots, artifact["text"])
    render_errors = [
        item
        for item in report.get("render_diagnostics", [])
        if isinstance(item, dict) and item.get("severity") == "error"
    ]
    pdf_result = _render_pdf_and_previews(output_path, output_dir=output_dir, case_id=case_id)

    channel_issues: list[str] = []
    if render_errors:
        channel_issues.append(f"render_error_diagnostics:{len(render_errors)}")
    if missing_text_slots:
        channel_issues.append(f"applied_text_missing_from_output:{len(missing_text_slots)}")
    if artifact["image_count"] < len(applied_image_slots):
        channel_issues.append(f"applied_image_missing_from_output:{len(applied_image_slots) - artifact['image_count']}")
    if artifact.get("oversized_image_count", 0):
        channel_issues.append(f"xlsx_image_display_oversized:{artifact['oversized_image_count']}")
    if pdf_result.get("conversion_error"):
        channel_issues.append(f"pdf_conversion_failed:{pdf_result['conversion_error']}")

    ledger_counts = _ledger_counts(report)
    review_flags: list[str] = []
    if ledger_counts.get("unresolved", 0):
        review_flags.append(f"unresolved_slots:{ledger_counts['unresolved']}")
    if ledger_counts.get("rejected", 0):
        review_flags.append(f"rejected_decisions:{ledger_counts['rejected']}")
    if artifact["residual_marker_count"]:
        review_flags.append(f"residual_markers:{artifact['residual_marker_count']}")

    return {
        "artifact_status": "failed" if channel_issues else "review" if review_flags else "passed",
        "channel_issues": channel_issues,
        "review_flags": review_flags,
        "report_counts": report.get("counts") or {},
        "ledger_counts": ledger_counts,
        "applied_text_count": len(applied_text_slots),
        "applied_image_count": len(applied_image_slots),
        "actual_image_count": artifact["image_count"],
        "embedded_drawing_count": artifact.get("drawing_count", 0),
        "missing_applied_text_slots": missing_text_slots,
        "residual_marker_count": artifact["residual_marker_count"],
        "residual_marker_examples": artifact["residual_marker_examples"],
        "xlsx_image_display_extents_px": artifact.get("xlsx_image_display_extents_px", []),
        "pdf_path": pdf_result.get("pdf_path"),
        "preview_dir": pdf_result.get("preview_dir"),
        "pdf_page_count": pdf_result.get("page_count"),
        "pdf_conversion_error": pdf_result.get("conversion_error"),
    }


def _inspect_docx(output_path: Path) -> dict[str, Any]:
    document = Document(output_path)
    text_parts: list[str] = []
    for paragraph in document.paragraphs:
        text_parts.append(paragraph.text)
    for table in document.tables:
        for row in table.rows:
            text_parts.extend(cell.text for cell in row.cells)
    for section in document.sections:
        for part in (section.header, section.footer):
            text_parts.extend(paragraph.text for paragraph in part.paragraphs)
            for table in part.tables:
                for row in table.rows:
                    text_parts.extend(cell.text for cell in row.cells)

    media_count = 0
    drawing_count = 0
    with ZipFile(output_path) as archive:
        media_count = len([name for name in archive.namelist() if name.startswith("word/media/")])
        for name in archive.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                drawing_count += archive.read(name).decode("utf-8", errors="ignore").count("<w:drawing")

    text = "\n".join(text_parts)
    return {
        "text": text,
        "image_count": media_count,
        "drawing_count": drawing_count,
        **_residual_markers(text),
    }


def _inspect_xlsx(output_path: Path) -> dict[str, Any]:
    workbook = load_workbook(output_path)
    text_parts: list[str] = []
    image_count = 0
    for worksheet in workbook.worksheets:
        image_count += len(getattr(worksheet, "_images", []))
        for row in worksheet.iter_rows():
            for cell in row:
                if cell.value not in (None, ""):
                    text_parts.append(str(cell.value))

    extents = _xlsx_display_extents(output_path)
    oversized_count = sum(1 for width, height in extents if width > OVERSIZED_XLSX_IMAGE_PX or height > OVERSIZED_XLSX_IMAGE_PX)
    text = "\n".join(text_parts)
    return {
        "text": text,
        "image_count": image_count,
        "drawing_count": len(extents),
        "xlsx_image_display_extents_px": [[round(width, 1), round(height, 1)] for width, height in extents],
        "oversized_image_count": oversized_count,
        **_residual_markers(text),
    }


def _xlsx_display_extents(output_path: Path) -> list[tuple[float, float]]:
    extents: list[tuple[float, float]] = []
    with ZipFile(output_path) as archive:
        for name in archive.namelist():
            if not name.startswith("xl/drawings/") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8", errors="ignore")
            for match in DRAWING_EXT_RE.finditer(xml):
                extents.append((int(match.group("cx")) / EMU_PER_PIXEL, int(match.group("cy")) / EMU_PER_PIXEL))
    return extents


def _render_pdf_and_previews(output_path: Path, *, output_dir: Path, case_id: str) -> dict[str, Any]:
    pdf_dir = output_dir / "pdf"
    preview_dir = output_dir / "previews" / case_id
    pdf_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    profile = f"file:///tmp/lo_profile_agentic_physical_{case_id}"
    try:
        subprocess.run(
            [
                "soffice",
                f"-env:UserInstallation={profile}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(pdf_dir),
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        pdf_path = pdf_dir / f"{output_path.stem}.pdf"
        subprocess.run(
            ["pdftoppm", "-png", "-r", "120", str(pdf_path), str(preview_dir / "page")],
            check=True,
            capture_output=True,
            text=True,
        )
        page_count = len(sorted(preview_dir.glob("page*.png")))
        return {
            "pdf_path": str(pdf_path),
            "preview_dir": str(preview_dir),
            "page_count": page_count,
            "conversion_error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pdf_path": None,
            "preview_dir": str(preview_dir),
            "page_count": 0,
            "conversion_error": f"{type(exc).__name__}: {exc}",
        }


def _accepted_text_values(report: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    decisions = report.get("decisions", {}).get("accepted", [])
    for item in decisions:
        if not isinstance(item, dict):
            continue
        if item.get("decision_type") != "text_fill":
            continue
        value = item.get("value")
        if isinstance(value, str) and value:
            values[str(item.get("slot_id"))] = value
    return values


def _missing_applied_texts(values: dict[str, str], applied_slots: set[str], output_text: str) -> list[str]:
    normalized_output = _normalize_match_text(output_text)
    missing: list[str] = []
    for slot_id in sorted(applied_slots):
        value = values.get(slot_id)
        if not value:
            continue
        normalized_value = _normalize_match_text(value)
        needle = normalized_value[: min(len(normalized_value), 40)]
        if needle and needle in normalized_output:
            continue
        fragments = _value_match_fragments(value)
        if fragments and all(fragment in normalized_output for fragment in fragments):
            continue
        if needle:
            missing.append(slot_id)
    return missing


def _normalize_match_text(value: str) -> str:
    value = re.sub(r"\s+", "", value)
    return value.translate(str.maketrans("", "", "，。；;：:、,.（）()【】[]"))


def _value_match_fragments(value: str) -> list[str]:
    fragments: list[str] = []
    for line in value.splitlines():
        line = re.sub(r"^\s*[（(]?[一二三四五六七八九十\d]+[）).、]\s*", "", line)
        line = _normalize_match_text(line)
        if len(line) >= 4:
            fragments.append(line)
    return fragments


def _residual_markers(text: str) -> dict[str, Any]:
    markers = [*TEXT_PLACEHOLDER_RE.findall(text), *BLANK_MARKER_RE.findall(text)]
    return {
        "residual_marker_count": len(markers),
        "residual_marker_examples": markers[:5],
    }


def _ledger_counts(report: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in report.get("target_ledger", []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("render_status") or item.get("decision_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _build_summary(*, manifest_path: Path, output_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "case_count": len(results),
        "passed": sum(1 for item in results if item.get("artifact_status") == "passed"),
        "review": sum(1 for item in results if item.get("artifact_status") == "review"),
        "failed": sum(1 for item in results if item.get("artifact_status") == "failed"),
        "channel_issue_case_count": sum(1 for item in results if item.get("channel_issues")),
        "review_flag_case_count": sum(1 for item in results if item.get("review_flags")),
    }
    return {
        "schema_name": "agentic_physical_acceptance_matrix",
        "manifest_path": str(manifest_path),
        "output_dir": str(output_dir),
        "counts": counts,
    }


def _write_outputs(output_dir: Path, summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    (output_dir / "physical_acceptance_summary.json").write_text(
        json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(output_dir / "physical_acceptance_summary.csv", results)
    (output_dir / "physical_acceptance_summary.md").write_text(_markdown(summary, results), encoding="utf-8")


def _write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "case_id",
        "artifact_status",
        "execution_status",
        "channel_issues",
        "review_flags",
        "applied_text_count",
        "applied_image_count",
        "actual_image_count",
        "pdf_page_count",
        "residual_marker_count",
        "output_path",
        "pdf_path",
        "preview_dir",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in results:
            row = {field: item.get(field) for field in fields}
            row["channel_issues"] = ";".join(item.get("channel_issues") or [])
            row["review_flags"] = ";".join(item.get("review_flags") or [])
            writer.writerow(row)


def _markdown(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    lines = [
        "# Agentic Physical Acceptance Matrix",
        "",
        f"- Manifest: `{summary['manifest_path']}`",
        f"- Output dir: `{summary['output_dir']}`",
        f"- Counts: `{summary['counts']}`",
        "",
        "| case | status | channel issues | review flags | text | images | pages |",
        "|---|---:|---|---|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            "| {case_id} | {status} | {issues} | {flags} | {text_count} | {image_count}/{actual_images} | {pages} |".format(
                case_id=item["case_id"],
                status=item["artifact_status"],
                issues="<br>".join(item.get("channel_issues") or []) or "-",
                flags="<br>".join(item.get("review_flags") or []) or "-",
                text_count=item.get("applied_text_count", 0),
                image_count=item.get("applied_image_count", 0),
                actual_images=item.get("actual_image_count", 0),
                pages=item.get("pdf_page_count", 0),
            )
        )
    return "\n".join(lines) + "\n"


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


if __name__ == "__main__":
    main()
