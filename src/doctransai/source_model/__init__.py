from __future__ import annotations

from doctransai.source_model.adapter import (
    AdaptedSourceModel,
    SourceModelAdaptationError,
    adapt_source_corpus,
)
from doctransai.source_model.instances import (
    build_source_instance_index,
    constraint_scoped_instance_for_asset,
    constraint_scoped_instance_for_provenance,
    constraint_scoped_instance_for_record,
)

__all__ = [
    "AdaptedSourceModel",
    "SourceModelAdaptationError",
    "adapt_source_corpus",
    "build_source_instance_index",
    "constraint_scoped_instance_for_asset",
    "constraint_scoped_instance_for_provenance",
    "constraint_scoped_instance_for_record",
]
