from __future__ import annotations

from doctransai.mapping.agent_resolver import (
    AgentCandidatePacket,
    AgentDecision,
    AgentResolutionError,
    AgentSlotPacket,
    prepare_agent_review_slot_packets,
    prepare_agent_slot_packets,
    prepare_agent_shared_context,
    resolve_mapping_decisions,
)
from doctransai.mapping.candidate_builder import SlotCandidatePacket, build_slot_candidate_packets
from doctransai.mapping.cluster_planner import (
    RepeatRegionClusterPlan,
    SourceClusterPlan,
    SourceClusterPlanningResult,
    SourceInstancePlan,
    build_source_cluster_plan,
)
from doctransai.mapping.full_agent_context import (
    FULL_AGENT_CONTEXT_SCHEMA_VERSION,
    NAVIGATION_CONTEXT_AUTHORITY,
    build_full_agent_context,
)
from doctransai.mapping.orchestrator import build_render_plan_with_agent, build_render_plan_with_decisions
from doctransai.mapping.render_plan_assembler import SlotActions, assemble_slot_actions
from doctransai.mapping.review_policy import is_risky_auto_fill, select_review_text_fills
from doctransai.mapping.slot_decisions import SlotDecision, resolve_slot_candidate_packets
from doctransai.mapping.structural_candidates import build_text_candidates_for_slot
from doctransai.mapping.type_inference import infer_slot_value_type, infer_source_value_type

__all__ = [
    "AgentCandidatePacket",
    "AgentDecision",
    "AgentResolutionError",
    "AgentSlotPacket",
    "SlotActions",
    "SlotCandidatePacket",
    "SlotDecision",
    "RepeatRegionClusterPlan",
    "SourceClusterPlan",
    "SourceClusterPlanningResult",
    "SourceInstancePlan",
    "FULL_AGENT_CONTEXT_SCHEMA_VERSION",
    "NAVIGATION_CONTEXT_AUTHORITY",
    "assemble_slot_actions",
    "build_full_agent_context",
    "build_render_plan_with_agent",
    "build_render_plan_with_decisions",
    "build_slot_candidate_packets",
    "build_source_cluster_plan",
    "build_text_candidates_for_slot",
    "infer_slot_value_type",
    "infer_source_value_type",
    "is_risky_auto_fill",
    "prepare_agent_review_slot_packets",
    "prepare_agent_slot_packets",
    "prepare_agent_shared_context",
    "resolve_mapping_decisions",
    "resolve_slot_candidate_packets",
    "select_review_text_fills",
]
