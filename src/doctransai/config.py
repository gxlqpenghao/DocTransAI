"""Runtime settings for the document-tool path; no user-specific defaults."""
from dataclasses import dataclass
from pathlib import Path
import os
import sys


@dataclass(frozen=True)
class RuntimeConfig:
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
        if min(self.max_steps, self.max_seconds, self.max_output_tokens,
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
