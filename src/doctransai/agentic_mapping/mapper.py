from __future__ import annotations

import base64
import inspect
import json
import mimetypes
from pathlib import Path
from typing import Any, Callable

from doctransai.agentic_mapping.decisions import AgentDecision, parse_agent_decisions
from doctransai.llm.client import generate_text_with_doctransai_llm

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "agentic_mapping_policy.md"


DecisionClient = Callable[..., str | dict[str, Any] | list[Any]]


def map_slots_with_agent(
    evidence_package: dict[str, Any],
    *,
    decision_client: DecisionClient | None = None,
) -> list[AgentDecision]:
    if decision_client is None:
        decision_client = generate_text_with_doctransai_llm

    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    request_payload = {"evidence_package": evidence_package}
    user_prompt = "INPUT_JSON:\n" + json.dumps(request_payload, ensure_ascii=False, sort_keys=True)
    user_parts = _user_parts(user_prompt, evidence_package)

    raw_response = _call_decision_client(
        decision_client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        user_parts=user_parts,
    )
    return parse_agent_decisions(_decision_items(raw_response))


def _decision_items(raw_response: str | dict[str, Any] | list[Any]) -> list[Any]:
    if isinstance(raw_response, str):
        payload: Any = json.loads(raw_response)
    else:
        payload = raw_response

    if isinstance(payload, dict):
        decisions = payload.get("decisions", [])
        if not isinstance(decisions, list):
            raise ValueError("Agent response field 'decisions' must be a list.")
        return decisions

    if isinstance(payload, list):
        return payload

    raise ValueError("Agent response must be a JSON object with decisions or a decision list.")


def _call_decision_client(
    decision_client: DecisionClient,
    *,
    system_prompt: str,
    user_prompt: str,
    user_parts: list[dict[str, Any]],
) -> str | dict[str, Any] | list[Any]:
    if _accepts_keyword(decision_client, "user_parts"):
        return decision_client(system_prompt=system_prompt, user_prompt=user_prompt, user_parts=user_parts)
    return decision_client(system_prompt=system_prompt, user_prompt=user_prompt)


def _accepts_keyword(decision_client: DecisionClient, keyword: str) -> bool:
    try:
        signature = inspect.signature(decision_client)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD or name == keyword
        for name, parameter in signature.parameters.items()
    )


def _user_parts(user_prompt: str, evidence_package: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    for page_image in _page_images(evidence_package):
        data_url = _image_data_url(page_image.get("image_ref"))
        if data_url is None:
            continue
        parts.append({"type": "image_url", "image_url": {"url": data_url}})
    return parts


def _page_images(evidence_package: dict[str, Any]) -> list[dict[str, Any]]:
    page_images: list[dict[str, Any]] = []
    for side in ("source", "template"):
        raw_items = evidence_package.get(side, {}).get("page_images", [])
        if isinstance(raw_items, list):
            page_images.extend(item for item in raw_items if isinstance(item, dict))
    return page_images


def _image_data_url(image_ref: Any) -> str | None:
    if not image_ref:
        return None
    path = Path(str(image_ref)).expanduser()
    if not path.exists() or not path.is_file():
        return None
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
