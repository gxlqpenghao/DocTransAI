"""Runtime settings for the document-tool path; no user-specific defaults."""
from dataclasses import dataclass
from pathlib import Path
import os
import math
import sys


@dataclass(frozen=True)
class RuntimeConfig:
    # Independent semantic review is opt-in for ordinary v1 conversion.
    review_enabled: bool = False
    review_max_steps: int = 6
    repair_max_steps: int = 4
    max_repair_rounds: int = 1
    max_steps: int = 12
    max_seconds: float = 900
    max_output_tokens: int = 5000
    initial_source_chars: int = 50000
    initial_source_pages: int = 6
    initial_source_assets: int = 12
    initial_source_max_bytes: int = 8_000_000
    auto_preview_max_pages: int = 8
    env_file: Path | None = None
    model: str = "kimi-k3"
    reasoning_effort: str = "high"
    render_script: Path | None = None
    render_python: str = sys.executable
    pdftoppm: str = "pdftoppm"
    render_timeout: float = 120
    render_revision: str = "1"
    # Optional local model-request diagnostics; observation only, off by default.
    model_diagnostics: bool = False

    def __post_init__(self):
        if not all(math.isfinite(x) for x in (self.max_seconds, self.max_steps, self.review_max_steps, self.repair_max_steps, self.render_timeout, self.max_output_tokens, self.initial_source_chars, self.initial_source_pages, self.initial_source_assets, self.initial_source_max_bytes, self.auto_preview_max_pages)):
            raise ValueError("Runtime budgets must be finite")
        if not 0 <= self.max_repair_rounds <= 2:
            raise ValueError("max_repair_rounds must be between 0 and 2")
        if min(self.review_max_steps, self.repair_max_steps, self.max_steps, self.max_seconds, self.max_output_tokens,
               self.initial_source_chars, self.initial_source_pages, self.initial_source_assets,
               self.initial_source_max_bytes, self.auto_preview_max_pages, self.render_timeout) <= 0:
            raise ValueError("Runtime budgets must be positive")
        if self.model != "kimi-k3":
            raise ValueError("The v1 document-tools path uses the fixed kimi-k3 model")
        if self.reasoning_effort not in ("low", "high", "max"):
            raise ValueError("reasoning_effort must be one of: low, high, max")

    @classmethod
    def from_environment(cls, **overrides):
        env_file = overrides.get("env_file")
        file_effort = None
        if env_file is not None and Path(env_file).is_file():
            for raw_line in Path(env_file).read_text(encoding="utf-8").splitlines():
                key, separator, value = raw_line.partition("=")
                if separator and key.strip() == "DOCTRANSAI_LLM_REASONING_EFFORT":
                    file_effort = value.strip().strip('"').strip("'")
                    break
        values = dict(render_script=Path(os.environ["DOCTRANSAI_DOCX_RENDERER"]).expanduser()
                      if os.environ.get("DOCTRANSAI_DOCX_RENDERER") else None,
                      render_python=os.environ.get("DOCTRANSAI_RENDER_PYTHON", sys.executable),
                      pdftoppm=os.environ.get("DOCTRANSAI_PDFTOPPM", "pdftoppm"),
                      render_revision=os.environ.get("DOCTRANSAI_RENDER_REVISION", "1"),
                      reasoning_effort=os.environ.get("DOCTRANSAI_LLM_REASONING_EFFORT") or file_effort or "high",
                      model_diagnostics=os.environ.get("DOCTRANSAI_MODEL_DIAGNOSTICS", "").strip().lower()
                      in ("1", "true", "on", "yes"))
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)
