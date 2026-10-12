"""Clean agent-centric mapping skeleton."""

from doctransai.agentic_mapping.assembler import assemble_render_plan_from_decisions
from doctransai.agentic_mapping.context import build_evidence_package
from doctransai.agentic_mapping.decision_repair import repair_duplicate_decisions
from doctransai.agentic_mapping.decisions import AgentDecision, parse_agent_decisions
from doctransai.agentic_mapping.mapper import map_slots_with_agent
from doctransai.agentic_mapping.template_targets import build_template_targets
from doctransai.agentic_mapping.validator import ValidationResult, validate_agent_decisions
from doctransai.agentic_mapping.visual_discovery import discover_template_visual_targets

__all__ = [
    "AgentDecision",
    "ValidationResult",
    "assemble_render_plan_from_decisions",
    "build_evidence_package",
    "build_template_targets",
    "discover_template_visual_targets",
    "map_slots_with_agent",
    "parse_agent_decisions",
    "repair_duplicate_decisions",
    "validate_agent_decisions",
]
