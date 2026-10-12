from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from doctransai.data_layer.models import SourceCorpus


SeverityLevel = Literal["info", "warning", "error"]
GateAction = Literal["allow", "warn", "fail"]
GateTrigger = Literal["warn", "fail"]

_SEVERITY_RANKS: dict[str, int] = {
    "info": 0,
    "warning": 1,
    "warn": 1,
    "error": 2,
    "fatal": 2,
}


@dataclass(slots=True)
class BundleGateFinding:
    diagnostic_id: str
    severity: str | None
    code: str | None
    message: str | None
    phase: str | None
    producer: str | None
    diagnostic_field: str | None = None
    raw_record: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BundleGateResult:
    action: GateAction
    threshold: SeverityLevel
    on_trigger: GateTrigger
    findings: list[BundleGateFinding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.action == "fail"


def evaluate_bundle_gate(
    corpus: SourceCorpus,
    *,
    minimum_severity: SeverityLevel = "error",
    on_trigger: GateTrigger = "fail",
) -> BundleGateResult:
    threshold_rank = _severity_rank(minimum_severity, validate=True)
    findings = [
        _finding_from_record(record)
        for record in corpus.diagnostics
        if _severity_rank(record.get("severity")) >= threshold_rank
    ]
    if not findings:
        return BundleGateResult(action="allow", threshold=minimum_severity, on_trigger=on_trigger)
    return BundleGateResult(action=on_trigger, threshold=minimum_severity, on_trigger=on_trigger, findings=findings)


def _finding_from_record(record: dict[str, Any]) -> BundleGateFinding:
    return BundleGateFinding(
        diagnostic_id=str(record.get("diagnostic_id", "")),
        severity=_optional_string(record.get("severity")),
        code=_optional_string(record.get("code")),
        message=_optional_string(record.get("message")),
        phase=_optional_string(record.get("phase")),
        producer=_optional_string(record.get("producer")),
        diagnostic_field=_optional_string(record.get("field")),
        raw_record=dict(record),
    )


def _severity_rank(value: object, *, validate: bool = False) -> int:
    normalized = _normalize_severity(value)
    if normalized in _SEVERITY_RANKS:
        return _SEVERITY_RANKS[normalized]
    if validate:
        raise ValueError(f"Unsupported severity: {value}")
    return _SEVERITY_RANKS["info"]


def _normalize_severity(value: object) -> str:
    if value is None:
        return "info"
    return str(value).strip().lower()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
