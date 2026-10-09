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
    reasoning_effort: str | None = None
    temperature: float | str | None = None
    llm_timeout_seconds: float | None = None
    token_parameter: str | None = None
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
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError('Model must be a nonempty provider model ID')
        from .settings import reasoning_for_model
        object.__setattr__(self, 'reasoning_effort', reasoning_for_model(self.model, self.reasoning_effort))
        if self.temperature not in (None, 'omit') and (not math.isfinite(float(self.temperature)) or float(self.temperature) < 0):
            raise ValueError('Temperature must be a nonnegative finite number or omit')
        if self.llm_timeout_seconds is not None and (not math.isfinite(self.llm_timeout_seconds) or self.llm_timeout_seconds <= 0):
            raise ValueError('LLM timeout must be positive and finite')
        if self.token_parameter not in (None, 'max_tokens', 'max_completion_tokens'):
            raise ValueError('Token parameter must be max_tokens or max_completion_tokens')

    @classmethod
    def from_environment(cls, **overrides):
        from .settings import env_values, setting
        file_values = env_values(overrides.get('env_file'))
        fields = {'DOCTRANSAI_LLM_MODEL':'model', 'DOCTRANSAI_LLM_MAX_TOKENS':'max_output_tokens',
                  'DOCTRANSAI_LLM_REASONING_EFFORT':'reasoning_effort', 'DOCTRANSAI_LLM_TEMPERATURE':'temperature',
                  'DOCTRANSAI_LLM_TIMEOUT_SECONDS':'llm_timeout_seconds', 'DOCTRANSAI_LLM_TOKEN_PARAMETER':'token_parameter'}
        def get(name, default=None):
            explicit = overrides.get(fields.get(name))
            return explicit if explicit is not None else setting(name, file_values, default)
        default_tokens = overrides.pop('_default_output_tokens', 5000)
        renderer = get('DOCTRANSAI_DOCX_RENDERER')
        temperature = get('DOCTRANSAI_LLM_TEMPERATURE')
        values = dict(env_file=Path(get('DOCTRANSAI_ENV_FILE')) if get('DOCTRANSAI_ENV_FILE') else None,
                      model=get('DOCTRANSAI_LLM_MODEL', 'kimi-k3'),
                      max_output_tokens=int(get('DOCTRANSAI_LLM_MAX_TOKENS', default_tokens)),
                      reasoning_effort=get('DOCTRANSAI_LLM_REASONING_EFFORT'),
                      temperature=temperature if temperature in (None, 'omit') else float(temperature),
                      llm_timeout_seconds=float(get('DOCTRANSAI_LLM_TIMEOUT_SECONDS', 180)),
                      token_parameter=get('DOCTRANSAI_LLM_TOKEN_PARAMETER', 'max_tokens'),
                      render_script=Path(renderer).expanduser() if renderer else None,
                      render_python=get('DOCTRANSAI_RENDER_PYTHON', sys.executable),
                      pdftoppm=get('DOCTRANSAI_PDFTOPPM', 'pdftoppm'),
                      render_revision=get('DOCTRANSAI_RENDER_REVISION', '1'),
                      model_diagnostics=get('DOCTRANSAI_MODEL_DIAGNOSTICS', '').lower() in ('1','true','on','yes'))
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)
