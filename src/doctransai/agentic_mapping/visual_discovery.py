from __future__ import annotations

from pathlib import Path
from typing import Any

from doctransai.agentic_mapping.mapper import (
    DecisionClient,
    _accepts_keyword,
    _build_request_inputs,
    _call_decision_client,
    _load_json_response,
)
from doctransai.llm.client import generate_text_with_doctransai_llm


_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "agentic_template_visual_discovery_policy.md"


def discover_template_visual_targets(
    evidence_package: dict[str, Any],
    *,
    discovery_client: DecisionClient | None = None,
) -> dict[str, Any]:
    if discovery_client is None:
        discovery_client = generate_text_with_doctransai_llm

    request_package = _template_discovery_package(evidence_package)
    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    client_accepts_user_parts = _accepts_keyword(discovery_client, "user_parts")
    user_prompt, user_parts = _build_request_inputs(
        request_package,
        system_prompt=system_prompt,
        client_accepts_user_parts=client_accepts_user_parts,
        use_default_provider_limit=discovery_client is generate_text_with_doctransai_llm,
    )
    raw_response = _call_decision_client(
        discovery_client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        user_parts=user_parts,
    )
    payload = _response_payload(raw_response)
    visual_targets = _visual_targets(payload, format_key=_template_format_key(evidence_package))
    return {
        "performed": True,
        "target_count": len(visual_targets),
        "agent_input": dict(request_package.get("agent_input", {})),
        "visual_targets": visual_targets,
    }


def _template_discovery_package(evidence_package: dict[str, Any]) -> dict[str, Any]:
    template = evidence_package.get("template", {})
    structured = template.get("structured", {})
    return {
        "schema_name": "agentic_template_visual_discovery_package",
        "template": {
            "structured": {
                "format_key": structured.get("format_key"),
                "slots": list(structured.get("slots", [])) if isinstance(structured.get("slots"), list) else [],
                "repeat_regions": (
                    list(structured.get("repeat_regions", []))
                    if isinstance(structured.get("repeat_regions"), list)
                    else []
                ),
                "header_regions": (
                    list(structured.get("header_regions", []))
                    if isinstance(structured.get("header_regions"), list)
                    else []
                ),
            },
            "page_images": list(template.get("page_images", [])) if isinstance(template.get("page_images"), list) else [],
            "page_image_index": dict(template.get("page_image_index", {}))
            if isinstance(template.get("page_image_index"), dict)
            else {},
        },
    }


def _response_payload(raw_response: str | dict[str, Any] | list[Any]) -> Any:
    if isinstance(raw_response, str):
        return _load_json_response(raw_response)
    return raw_response


def _visual_targets(payload: Any, *, format_key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        raw_targets = payload.get("visual_targets", [])
    else:
        raw_targets = payload
    if not isinstance(raw_targets, list):
        return []

    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_targets:
        if not isinstance(item, dict):
            continue
        target = _normalize_visual_target(item, format_key=format_key)
        if _looks_like_fixed_text_not_fillable(target):
            continue
        target_id = target.get("target_id")
        if not isinstance(target_id, str) or not target_id or target_id in seen:
            continue
        targets.append(target)
        seen.add(target_id)
    return targets


def _normalize_visual_target(item: dict[str, Any], *, format_key: str) -> dict[str, Any]:
    label = _text(item.get("label_or_nearby_text") or item.get("label") or item.get("nearby_text"))
    target_id = _text(item.get("target_id")) or _target_id(label)
    raw_visual_target = item.get("visual_target")
    visual_target = dict(raw_visual_target) if isinstance(raw_visual_target, dict) else {}
    if format_key and not visual_target.get("format_key"):
        visual_target["format_key"] = format_key
    visual_target.setdefault("target_kind", "visual_text_anchor")
    if label and not visual_target.get("label_or_nearby_text"):
        visual_target["label_or_nearby_text"] = label
    if item.get("page_index") is not None and visual_target.get("page_index") is None:
        visual_target["page_index"] = item.get("page_index")
    if item.get("approx_location") is not None and visual_target.get("approx_location") is None:
        visual_target["approx_location"] = item.get("approx_location")

    return _compact(
        {
            "target_id": target_id,
            "label_or_nearby_text": label,
            "expected_content_type": _text(item.get("expected_content_type")),
            "approx_location": _text(item.get("approx_location")),
            "visual_reason": _text(item.get("visual_reason") or item.get("reason")),
            "visual_target": visual_target,
        }
    )


def _template_format_key(evidence_package: dict[str, Any]) -> str:
    value = (
        evidence_package.get("template", {})
        .get("structured", {})
        .get("format_key")
    )
    return value if isinstance(value, str) and value else "docx"


def _target_id(label: str | None) -> str | None:
    if not label:
        return None
    compact = "".join(ch for ch in label if not ch.isspace())
    compact = compact.replace("：", "").replace(":", "")
    if not compact:
        return None
    return f"visual-target-{compact[:40]}"


def _looks_like_fixed_text_not_fillable(target: dict[str, Any]) -> bool:
    reason = " ".join(
        str(value)
        for value in (
            target.get("label_or_nearby_text"),
            target.get("approx_location"),
            target.get("visual_reason"),
            target.get("visual_target", {}).get("approx_location")
            if isinstance(target.get("visual_target"), dict)
            else None,
        )
        if value
    ).casefold()
    if not reason:
        return False

    fillable_markers = (
        "空白",
        "空格",
        "空单元格",
        "待填",
        "填写",
        "填入",
        "下划线",
        "横线",
        "blank",
        "empty",
        "fillable",
        "underline",
    )
    if any(marker in reason for marker in fillable_markers):
        return False

    fixed_text_markers = (
        "标题",
        "表头",
        "页眉",
        "固定文本",
        "已填",
        "现有文本",
        "title",
        "heading",
        "header",
        "fixed text",
        "already filled",
    )
    return any(marker in reason for marker in fixed_text_markers)


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, {}, [])
    }


__all__ = ["discover_template_visual_targets"]
