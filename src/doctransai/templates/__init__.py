from __future__ import annotations

from doctransai.templates.analyzers import analyze_template
from doctransai.templates.sample_normalization import TemplateNormalizationResult, normalize_sample_template
from doctransai.templates.template_materialization import TemplateMaterializationResult, materialize_target_template

__all__ = [
    "TemplateMaterializationResult",
    "TemplateNormalizationResult",
    "analyze_template",
    "materialize_target_template",
    "normalize_sample_template",
]
