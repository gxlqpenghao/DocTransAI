from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


_PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "agent_mapping_policy.md"
_SECTION_RE = re.compile(
    r"<!--\s*section:\s*(?P<name>[a-zA-Z0-9_\-]+)\s*-->\s*(?P<body>.*?)\s*<!--\s*endsection\s*-->",
    re.DOTALL,
)


class PromptPolicyError(ValueError):
    pass


def build_mapping_system_prompt() -> str:
    return _prompt_section("mapping_system")


def build_mapping_user_prompt(slot_payload: dict[str, Any]) -> str:
    input_json = (
        json.dumps(slot_payload, ensure_ascii=False, separators=(",", ":"))
        if _should_minify_input_json(slot_payload)
        else json.dumps(slot_payload, ensure_ascii=False, indent=2)
    )
    return _render_section(
        "mapping_user",
        input_json=input_json,
    )


def build_repair_system_prompt() -> str:
    return _prompt_section("repair_system")


def build_mapping_repair_prompt(
    *,
    slot_payload: dict[str, Any],
    previous_output: str,
    validation_errors: list[str],
) -> str:
    return _render_section(
        "repair_user",
        validation_errors="\n".join(f"- {item}" for item in validation_errors),
        input_json=(
            json.dumps(slot_payload, ensure_ascii=False, separators=(",", ":"))
            if _should_minify_input_json(slot_payload)
            else json.dumps(slot_payload, ensure_ascii=False, indent=2)
        ),
        previous_output=previous_output,
    )


def _should_minify_input_json(slot_payload: dict[str, Any]) -> bool:
    packaging = slot_payload.get("agent_input_packaging")
    if isinstance(packaging, dict) and packaging.get("mode") in {"compact_slot_packets", "preflight_blocked"}:
        return True
    return "full_agent_context" in slot_payload and not any(
        key in slot_payload
        for key in [
            "source_overview",
            "source_document_view",
            "template_overview",
            "source_instance_overview",
            "source_cluster_plan",
        ]
    )


def prompt_policy_path() -> Path:
    return _PROMPT_FILE


@lru_cache(maxsize=1)
def _prompt_sections() -> dict[str, str]:
    try:
        text = _PROMPT_FILE.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PromptPolicyError(f"Prompt policy file not found: {_PROMPT_FILE}") from exc

    sections = {
        match.group("name"): match.group("body").strip()
        for match in _SECTION_RE.finditer(text)
    }
    required = {"mapping_system", "mapping_user", "repair_system", "repair_user"}
    missing = sorted(required - set(sections))
    if missing:
        raise PromptPolicyError(f"Prompt policy file is missing sections: {', '.join(missing)}")
    return sections


def _prompt_section(name: str) -> str:
    sections = _prompt_sections()
    try:
        return sections[name]
    except KeyError as exc:
        raise PromptPolicyError(f"Prompt policy section not found: {name}") from exc


def _render_section(name: str, **values: str) -> str:
    rendered = _prompt_section(name)
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered
