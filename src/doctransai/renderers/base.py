from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from doctransai.models.render_plan import RenderPlan
from doctransai.renderers.models import RenderResult


@runtime_checkable
class Renderer(Protocol):
    format_key: str

    def render(
        self,
        plan: RenderPlan,
        *,
        bundle_dir: str | Path | None = None,
    ) -> RenderResult: ...
