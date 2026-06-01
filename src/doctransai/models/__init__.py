from __future__ import annotations

from doctransai.models.diagnostics import ReasonCode, Severity
from doctransai.models.mapping import (
    FieldCandidate,
    ImageCandidate,
    ResolvedSlot,
    ResolverDecision,
    UnresolvedSlot,
)
from doctransai.models.render_plan import (
    ImagePlacement,
    OutputRef,
    PlanDiagnostic,
    RenderPlan,
    RowPlan,
    TargetRef,
    TemplateRef,
    TextFill,
    render_plan_from_dict,
    render_plan_to_dict,
)
from doctransai.models.source import (
    ProvenanceRef,
    SourceDocument,
    SourceImageAsset,
    SourceModel,
    SourceRecord,
    SourceValue,
)
from doctransai.models.source_instance import SourceCluster, SourceInstance, SourceInstanceIndex
from doctransai.models.template import (
    HeaderDrivenRegion,
    RepeatRegion,
    SlotAddress,
    TemplateDiagnostic,
    TemplateModel,
    TemplateSlot,
)

__all__ = [
    "FieldCandidate",
    "HeaderDrivenRegion",
    "ImageCandidate",
    "ImagePlacement",
    "OutputRef",
    "PlanDiagnostic",
    "ProvenanceRef",
    "ReasonCode",
    "RenderPlan",
    "RepeatRegion",
    "ResolvedSlot",
    "ResolverDecision",
    "RowPlan",
    "Severity",
    "SlotAddress",
    "SourceCluster",
    "SourceDocument",
    "SourceImageAsset",
    "SourceInstance",
    "SourceInstanceIndex",
    "SourceModel",
    "SourceRecord",
    "SourceValue",
    "TargetRef",
    "TemplateDiagnostic",
    "TemplateModel",
    "TemplateRef",
    "TemplateSlot",
    "TextFill",
    "UnresolvedSlot",
    "render_plan_from_dict",
    "render_plan_to_dict",
]
