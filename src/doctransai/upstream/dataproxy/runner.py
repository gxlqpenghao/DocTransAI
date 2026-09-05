from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Callable

from doctransai.upstream.dataproxy.issue_report import (
    DataProxyIssueReport,
    create_dataproxy_issue_report,
    issue_report_from_exception,
)


DATAPROXY_CALLABLE_ENV = "DOCTRANSAI_DATAPROXY_CALLABLE"
DATAPROXY_PYTHONPATH_HINT = "<DataProxy checkout>/src"


@dataclass(frozen=True, slots=True)
class DataProxyRunnerConfig:
    callable_path: str | None = None
    operation: str = "bundle_generation"


class DataProxyBoundaryError(RuntimeError):
    def __init__(self, message: str, *, issue_report: DataProxyIssueReport) -> None:
        super().__init__(message)
        self.issue_report = issue_report


class DataProxyUnavailableError(DataProxyBoundaryError):
    pass


class DataProxyExecutionError(DataProxyBoundaryError):
    pass


def load_dataproxy_callable(
    config: DataProxyRunnerConfig | None = None,
) -> Callable[..., Any]:
    callable_path = resolve_dataproxy_callable_path(config)
    module_name, attribute_name = _split_callable_path(callable_path, config)

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        report = issue_report_from_exception(
            exc,
            category="unavailable",
            operation=_operation_name(config),
            summary=f"DataProxy module `{module_name}` is unavailable.",
            callable_path=callable_path,
            observed_behavior=(
                f"DocTransAI could not import `{module_name}` from `{callable_path}`."
            ),
            expected_behavior=(
                "DocTransAI should import the configured DataProxy callable after "
                f"setting PYTHONPATH={DATAPROXY_PYTHONPATH_HINT} or passing explicit config."
            ),
        )
        raise DataProxyUnavailableError(
            "Unable to import the configured DataProxy module "
            f"`{module_name}`. Ensure DataProxy is importable via "
            f"PYTHONPATH={DATAPROXY_PYTHONPATH_HINT} or provide a valid explicit "
            f"callable path. Original error: {type(exc).__name__}: {exc}",
            issue_report=report,
        ) from exc

    try:
        candidate = getattr(module, attribute_name)
    except AttributeError as exc:
        report = issue_report_from_exception(
            exc,
            category="unavailable",
            operation=_operation_name(config),
            summary=f"DataProxy callable `{callable_path}` is missing.",
            callable_path=callable_path,
            observed_behavior=(
                f"DocTransAI imported `{module_name}` but could not find `{attribute_name}`."
            ),
            expected_behavior="The configured DataProxy callable should exist on the imported module.",
        )
        raise DataProxyUnavailableError(
            f"Configured DataProxy callable `{callable_path}` does not exist.",
            issue_report=report,
        ) from exc

    if not callable(candidate):
        report = create_dataproxy_issue_report(
            category="unavailable",
            summary=f"DataProxy callable `{callable_path}` is not callable.",
            operation=_operation_name(config),
            callable_path=callable_path,
            observed_behavior=(
                f"DocTransAI resolved `{callable_path}`, but the target object is not callable."
            ),
            expected_behavior="The configured DataProxy target should be a callable entry point.",
        )
        raise DataProxyUnavailableError(
            f"Configured DataProxy target `{callable_path}` is not callable.",
            issue_report=report,
        )

    return candidate


def resolve_dataproxy_callable_path(config: DataProxyRunnerConfig | None = None) -> str:
    if config is not None and config.callable_path:
        return config.callable_path

    env_value = os.environ.get(DATAPROXY_CALLABLE_ENV)
    if env_value:
        return env_value

    report = create_dataproxy_issue_report(
        category="configuration",
        summary="DataProxy callable path is not configured.",
        operation=_operation_name(config),
        observed_behavior=(
            f"DocTransAI could not find a DataProxy callable path in `{DATAPROXY_CALLABLE_ENV}` "
            "or explicit runner config."
        ),
        expected_behavior=(
            "DocTransAI should resolve a DataProxy callable from explicit config or "
            f"`{DATAPROXY_CALLABLE_ENV}` while DataProxy is importable via "
            f"`PYTHONPATH={DATAPROXY_PYTHONPATH_HINT}`."
        ),
    )
    raise DataProxyUnavailableError(
        "DataProxy callable path is not configured. Set "
        f"`{DATAPROXY_CALLABLE_ENV}` and expose DataProxy with "
        f"`PYTHONPATH={DATAPROXY_PYTHONPATH_HINT}`, or pass explicit runner config.",
        issue_report=report,
    )


def run_dataproxy(
    *args: Any,
    config: DataProxyRunnerConfig | None = None,
    **kwargs: Any,
) -> Any:
    callable_path = resolve_dataproxy_callable_path(config)
    dataproxy_callable = load_dataproxy_callable(config)

    try:
        return dataproxy_callable(*args, **kwargs)
    except DataProxyBoundaryError:
        raise
    except Exception as exc:
        report = issue_report_from_exception(
            exc,
            operation=_operation_name(config),
            callable_path=callable_path,
            observed_behavior=(
                f"Calling `{callable_path}` raised {type(exc).__name__}: {exc}"
            ),
            expected_behavior=(
                "The configured DataProxy callable should execute successfully through "
                "DocTransAI's upstream boundary."
            ),
        )
        raise DataProxyExecutionError(
            f"DataProxy callable `{callable_path}` failed: {type(exc).__name__}: {exc}",
            issue_report=report,
        ) from exc


def _split_callable_path(
    callable_path: str,
    config: DataProxyRunnerConfig | None,
) -> tuple[str, str]:
    module_name, separator, attribute_name = callable_path.partition(":")
    if module_name and separator and attribute_name:
        return module_name, attribute_name

    report = create_dataproxy_issue_report(
        category="configuration",
        summary="DataProxy callable path is malformed.",
        operation=_operation_name(config),
        callable_path=callable_path,
        observed_behavior=(
            f"DocTransAI received `{callable_path}`, which is not in `module:function` format."
        ),
        expected_behavior="The DataProxy callable path should use `module:function` format.",
    )
    raise DataProxyUnavailableError(
        f"Malformed DataProxy callable path `{callable_path}`. Expected `module:function`.",
        issue_report=report,
    )


def _operation_name(config: DataProxyRunnerConfig | None) -> str:
    if config is None:
        return "bundle_generation"
    return config.operation


__all__ = [
    "DATAPROXY_CALLABLE_ENV",
    "DATAPROXY_PYTHONPATH_HINT",
    "DataProxyBoundaryError",
    "DataProxyExecutionError",
    "DataProxyRunnerConfig",
    "DataProxyUnavailableError",
    "load_dataproxy_callable",
    "resolve_dataproxy_callable_path",
    "run_dataproxy",
]
