from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Iterator


@dataclass(slots=True)
class WorkflowTimingStep:
    name: str
    elapsed_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowPerformanceMonitor:
    scope: str = "doctransai_bundle_to_output"
    steps: list[WorkflowTimingStep] = field(default_factory=list)
    _started_at: float = field(default_factory=perf_counter)

    @contextmanager
    def step(self, name: str, **metadata: Any) -> Iterator[dict[str, Any]]:
        step_metadata = dict(metadata)
        started_at = perf_counter()
        try:
            yield step_metadata
        finally:
            self.steps.append(
                WorkflowTimingStep(
                    name=name,
                    elapsed_ms=_elapsed_ms(started_at),
                    metadata={key: value for key, value in step_metadata.items() if value is not None},
                )
            )

    def report(self, *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "total_elapsed_ms": _elapsed_ms(self._started_at),
            "steps": [asdict(step) for step in self.steps],
            "summary": dict(summary or {}),
        }


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)
