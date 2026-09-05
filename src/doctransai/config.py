"""Runtime settings for the document-tool path; no user-specific defaults."""
from dataclasses import dataclass
from pathlib import Path
import os
import math
import sys


@dataclass(frozen=True)
class RuntimeConfig:
    review_enabled: bool = True
    review_max_steps: int = 6
    repair_max_steps: int = 4
    max_repair_rounds: int = 1
    max_steps: int = 12
    max_seconds: float = 900
    max_output_tokens: int = 5000
    initial_source_chars: int = 50000
    env_file: Path | None = None
    model: str | None = None
    render_script: Path | None = None
    render_python: str = sys.executable
    pdftoppm: str = "pdftoppm"
    render_timeout: float = 120
    render_revision: str = "1"

    def __post_init__(self):
        if not all(math.isfinite(x) for x in (self.max_seconds, self.max_steps, self.review_max_steps, self.repair_max_steps, self.render_timeout, self.max_output_tokens, self.initial_source_chars)):
            raise ValueError("Runtime budgets must be finite")
        if not 0 <= self.max_repair_rounds <= 2:
            raise ValueError("max_repair_rounds must be between 0 and 2")
        if min(self.review_max_steps, self.repair_max_steps, self.max_steps, self.max_seconds, self.max_output_tokens,
               self.initial_source_chars, self.render_timeout) <= 0:
            raise ValueError("Runtime budgets must be positive")

    @classmethod
    def from_environment(cls, **overrides):
        values = dict(render_script=Path(os.environ["DOCTRANSAI_DOCX_RENDERER"]).expanduser()
                      if os.environ.get("DOCTRANSAI_DOCX_RENDERER") else None,
                      render_python=os.environ.get("DOCTRANSAI_RENDER_PYTHON", sys.executable),
                      pdftoppm=os.environ.get("DOCTRANSAI_PDFTOPPM", "pdftoppm"),
                      render_revision=os.environ.get("DOCTRANSAI_RENDER_REVISION", "1"))
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)
