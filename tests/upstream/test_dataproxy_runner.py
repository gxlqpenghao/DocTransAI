from __future__ import annotations

import importlib
from types import ModuleType

import pytest

from doctransai.upstream.dataproxy import (
    DATAPROXY_CALLABLE_ENV,
    DATAPROXY_PYTHONPATH_HINT,
    DataProxyExecutionError,
    DataProxyRunnerConfig,
    DataProxyUnavailableError,
    load_dataproxy_callable,
    run_dataproxy,
)


def test_run_dataproxy_uses_explicit_callable_path(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("fake_dataproxy.runner")
    calls: list[tuple[str, str]] = []

    def build_bundle(source_path: str, output_dir: str) -> dict[str, str]:
        calls.append((source_path, output_dir))
        return {"bundle_path": f"{output_dir}/parsed_document_bundle.json"}

    module.build_bundle = build_bundle  # type: ignore[attr-defined]

    def fake_import_module(name: str) -> ModuleType:
        assert name == "fake_dataproxy.runner"
        return module

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    result = run_dataproxy(
        "/tmp/source.docx",
        output_dir="/tmp/out",
        config=DataProxyRunnerConfig(callable_path="fake_dataproxy.runner:build_bundle"),
    )

    assert result == {"bundle_path": "/tmp/out/parsed_document_bundle.json"}
    assert calls == [("/tmp/source.docx", "/tmp/out")]


def test_load_dataproxy_callable_reads_environment_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("fake_dataproxy.cli")

    def main(*, job_id: str) -> str:
        return f"job:{job_id}"

    module.main = main  # type: ignore[attr-defined]

    monkeypatch.setenv(DATAPROXY_CALLABLE_ENV, "fake_dataproxy.cli:main")
    monkeypatch.setattr(importlib, "import_module", lambda _: module)

    callable_obj = load_dataproxy_callable()

    assert callable_obj(job_id="run-7") == "job:run-7"


def test_run_dataproxy_raises_clear_error_when_configuration_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATAPROXY_CALLABLE_ENV, raising=False)

    with pytest.raises(DataProxyUnavailableError) as exc_info:
        run_dataproxy()

    message = str(exc_info.value)
    assert DATAPROXY_CALLABLE_ENV in message
    assert f"PYTHONPATH={DATAPROXY_PYTHONPATH_HINT}" in message

    report = exc_info.value.issue_report.to_dict()
    assert report["category"] == "configuration"
    assert report["expected_behavior"].startswith("DocTransAI should resolve")


def test_load_dataproxy_callable_reports_missing_module_with_pythonpath_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import_module(name: str) -> ModuleType:
        raise ModuleNotFoundError(f"No module named '{name}'")

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with pytest.raises(DataProxyUnavailableError) as exc_info:
        load_dataproxy_callable(
            DataProxyRunnerConfig(callable_path="missing_dataproxy.runner:build_bundle")
        )

    message = str(exc_info.value)
    assert "missing_dataproxy.runner" in message
    assert f"PYTHONPATH={DATAPROXY_PYTHONPATH_HINT}" in message

    report = exc_info.value.issue_report.to_dict()
    assert report["category"] == "unavailable"
    assert report["callable_path"] == "missing_dataproxy.runner:build_bundle"


def test_run_dataproxy_wraps_upstream_failures_with_issue_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("fake_dataproxy.runtime")

    def crash(*_: object, **__: object) -> None:
        raise ValueError("bad bundle shape")

    module.crash = crash  # type: ignore[attr-defined]
    monkeypatch.setattr(importlib, "import_module", lambda _: module)

    with pytest.raises(DataProxyExecutionError) as exc_info:
        run_dataproxy(config=DataProxyRunnerConfig(callable_path="fake_dataproxy.runtime:crash"))

    message = str(exc_info.value)
    assert "fake_dataproxy.runtime:crash" in message
    assert "ValueError: bad bundle shape" in message

    report = exc_info.value.issue_report.to_dict()
    assert report["category"] == "upstream_defect"
    assert report["callable_path"] == "fake_dataproxy.runtime:crash"
    assert report["exception"]["type"] == "ValueError"
