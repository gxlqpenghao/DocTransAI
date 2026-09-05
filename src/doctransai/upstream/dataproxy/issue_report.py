from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


DATAPROXY_BOUNDARY = "doctransai.upstream.dataproxy"
DATAPROXY_UPSTREAM_ROOT = "<configured DataProxy root>"


@dataclass(frozen=True, slots=True)
class ExceptionSummary:
    type: str
    message: str


@dataclass(frozen=True, slots=True)
class DataProxyIssueReport:
    category: str
    summary: str
    operation: str
    observed_behavior: str
    expected_behavior: str
    boundary: str = DATAPROXY_BOUNDARY
    upstream_root: str = DATAPROXY_UPSTREAM_ROOT
    callable_path: str | None = None
    file_paths: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    exception: ExceptionSummary | None = None
    recommended_action: str = (
        "Report the issue to the project owner and do not modify DataProxy source from DocTransAI."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_dataproxy_issue_report(
    *,
    category: str,
    summary: str,
    operation: str,
    observed_behavior: str,
    expected_behavior: str,
    callable_path: str | None = None,
    file_paths: list[str] | None = None,
    details: dict[str, Any] | None = None,
    exception: BaseException | None = None,
) -> DataProxyIssueReport:
    exception_summary = None
    if exception is not None:
        exception_summary = ExceptionSummary(
            type=type(exception).__name__,
            message=str(exception),
        )

    return DataProxyIssueReport(
        category=category,
        summary=summary,
        operation=operation,
        observed_behavior=observed_behavior,
        expected_behavior=expected_behavior,
        callable_path=callable_path,
        file_paths=list(file_paths or []),
        details=dict(details or {}),
        exception=exception_summary,
    )


def issue_report_from_exception(
    exception: BaseException,
    *,
    operation: str,
    observed_behavior: str,
    expected_behavior: str,
    category: str = "upstream_defect",
    summary: str | None = None,
    callable_path: str | None = None,
    file_paths: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> DataProxyIssueReport:
    return create_dataproxy_issue_report(
        category=category,
        summary=summary or f"DataProxy {operation} failed at the upstream boundary.",
        operation=operation,
        observed_behavior=observed_behavior,
        expected_behavior=expected_behavior,
        callable_path=callable_path,
        file_paths=file_paths,
        details=details,
        exception=exception,
    )


__all__ = [
    "DATAPROXY_BOUNDARY",
    "DATAPROXY_UPSTREAM_ROOT",
    "DataProxyIssueReport",
    "ExceptionSummary",
    "create_dataproxy_issue_report",
    "issue_report_from_exception",
]
