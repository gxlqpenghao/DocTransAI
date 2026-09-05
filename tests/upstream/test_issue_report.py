from __future__ import annotations

import json

from doctransai.upstream.dataproxy import (
    DATAPROXY_UPSTREAM_ROOT,
    create_dataproxy_issue_report,
    issue_report_from_exception,
)


def test_create_dataproxy_issue_report_is_structured_and_serializable() -> None:
    report = create_dataproxy_issue_report(
        category="upstream_defect",
        summary="DataProxy returned malformed bundle metadata.",
        operation="bundle_generation",
        observed_behavior="Bundle summary omitted document_count.",
        expected_behavior="Bundle summary should include document_count.",
        callable_path="dataproxy.pipeline:run",
        file_paths=["<DataProxy checkout>/src/dataproxy/pipeline.py"],
        details={"document_id": "doc-7"},
    )

    payload = report.to_dict()

    assert payload["upstream_root"] == DATAPROXY_UPSTREAM_ROOT
    assert payload["boundary"] == "doctransai.upstream.dataproxy"
    assert payload["file_paths"] == ["<DataProxy checkout>/src/dataproxy/pipeline.py"]
    assert payload["details"] == {"document_id": "doc-7"}
    assert json.loads(json.dumps(payload)) == payload


def test_issue_report_from_exception_captures_exception_metadata() -> None:
    try:
        raise RuntimeError("pipeline exploded")
    except RuntimeError as exc:
        report = issue_report_from_exception(
            exc,
            operation="bundle_generation",
            callable_path="dataproxy.pipeline:run",
            observed_behavior="The upstream runner aborted before writing a bundle.",
            expected_behavior="The upstream runner should write parsed_document_bundle.json.",
        )

    payload = report.to_dict()

    assert payload["category"] == "upstream_defect"
    assert payload["exception"]["type"] == "RuntimeError"
    assert payload["exception"]["message"] == "pipeline exploded"
