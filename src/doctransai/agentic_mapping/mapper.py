from __future__ import annotations

import base64
import copy
import inspect
import json
import mimetypes
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from doctransai.agentic_mapping.decisions import AgentDecision, parse_agent_decisions
from doctransai.llm.client import (
    DoctransaiLLMInputTooLargeError,
    DoctransaiLLMRequestTooLargeError,
    estimate_chat_input_chars,
    estimate_chat_request_bytes,
    generate_text_with_doctransai_llm,
    resolve_llm_input_char_limit,
    resolve_llm_request_body_limit_bytes,
)

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "agentic_mapping_policy.md"
DOCTRANSAI_AGENTIC_MAX_INLINE_PAGE_IMAGES_ENV = "DOCTRANSAI_AGENTIC_MAX_INLINE_PAGE_IMAGES"
DOCTRANSAI_AGENTIC_MAX_INLINE_IMAGE_CHARS_ENV = "DOCTRANSAI_AGENTIC_MAX_INLINE_IMAGE_CHARS"
DOCTRANSAI_AGENTIC_MAX_INLINE_IMAGE_TOTAL_CHARS_ENV = "DOCTRANSAI_AGENTIC_MAX_INLINE_IMAGE_TOTAL_CHARS"
DOCTRANSAI_AGENTIC_PROVIDER_MAX_INPUT_CHARS_ENV = "DOCTRANSAI_AGENTIC_PROVIDER_MAX_INPUT_CHARS"
DEFAULT_MAX_INLINE_PAGE_IMAGES = 0
DEFAULT_MAX_INLINE_IMAGE_CHARS = 180_000
DEFAULT_MAX_INLINE_IMAGE_TOTAL_CHARS = 720_000
DEFAULT_AGENTIC_PROVIDER_MAX_INPUT_CHARS = 3_000_000


DecisionClient = Callable[..., str | dict[str, Any] | list[Any]]


class AgentResponseParseError(ValueError):
    pass


def map_slots_with_agent(
    evidence_package: dict[str, Any],
    *,
    decision_client: DecisionClient | None = None,
) -> list[AgentDecision]:
    uses_default_client = decision_client is None
    if decision_client is None:
        decision_client = generate_text_with_doctransai_llm

    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    client_accepts_user_parts = _accepts_keyword(decision_client, "user_parts")
    user_prompt, user_parts = _build_request_inputs(
        evidence_package,
        system_prompt=system_prompt,
        client_accepts_user_parts=client_accepts_user_parts,
        use_default_provider_limit=uses_default_client,
    )

    raw_response = _call_decision_client(
        decision_client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        user_parts=user_parts,
    )
    payload = _response_payload(raw_response)
    evidence_package["visual_scan"] = _visual_scan(payload)
    return parse_agent_decisions(_decision_items(payload))


def _decision_items(raw_response: str | dict[str, Any] | list[Any]) -> list[Any]:
    payload = _response_payload(raw_response)

    if isinstance(payload, dict):
        decisions = payload.get("decisions", [])
        if not isinstance(decisions, list):
            raise ValueError("Agent response field 'decisions' must be a list.")
        return decisions

    if isinstance(payload, list):
        return payload

    raise ValueError("Agent response must be a JSON object with decisions or a decision list.")


def _response_payload(raw_response: str | dict[str, Any] | list[Any]) -> Any:
    if isinstance(raw_response, str):
        return _load_json_response(raw_response)
    return raw_response


def _visual_scan(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"performed": False, "reason": "agent_returned_decision_list_without_visual_scan"}
    raw_scan = payload.get("visual_scan")
    if not isinstance(raw_scan, dict):
        return {"performed": False, "reason": "agent_response_missing_visual_scan"}

    scan = dict(raw_scan)
    scan["performed"] = bool(scan.get("performed"))
    areas = scan.get("extra_fillable_areas")
    if not isinstance(areas, list):
        scan["extra_fillable_areas"] = []
    else:
        scan["extra_fillable_areas"] = [
            dict(item)
            for item in areas
            if isinstance(item, dict)
        ]
    return scan


def _load_json_response(raw_response: str) -> Any:
    candidates = _json_candidates(raw_response)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    preview = raw_response.strip().replace("\n", "\\n")[:500]
    raise AgentResponseParseError(f"Agent response is not valid JSON. Preview: {preview}")


def _json_candidates(raw_response: str) -> list[str]:
    stripped = raw_response.strip()
    candidates = [stripped]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced is not None:
        candidates.append(fenced.group(1).strip())
    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        end = stripped.rfind(closer)
        if start >= 0 and end > start:
            candidates.append(stripped[start : end + 1])
    return candidates


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


def _build_request_inputs(
    evidence_package: dict[str, Any],
    *,
    system_prompt: str,
    client_accepts_user_parts: bool,
    use_default_provider_limit: bool,
) -> tuple[str, list[dict[str, Any]]]:
    request_package, packaging = _agent_request_package(evidence_package)
    inline_images, skipped_page_images = _inline_page_images(request_package)
    while True:
        user_parts, agent_input = _user_parts(
            request_package,
            inline_images=inline_images,
            skipped_page_images=skipped_page_images,
            client_accepts_user_parts=client_accepts_user_parts,
        )
        agent_input["packaging"] = dict(packaging)
        evidence_package["agent_input"] = agent_input
        request_package["agent_input"] = agent_input
        user_prompt = _finalize_user_prompt(
            request_package,
            agent_input=agent_input,
            system_prompt=system_prompt,
            user_parts=user_parts,
            use_default_provider_limit=use_default_provider_limit,
        )
        over_limit_reason = _payload_over_limit_reason(agent_input)
        if over_limit_reason is None:
            return user_prompt, user_parts
        if inline_images:
            skipped_page_images.append(
                _skipped_inline_image_summary(
                    inline_images.pop(),
                    reason=over_limit_reason,
                )
            )
            continue
        _raise_payload_too_large(agent_input, over_limit_reason)


def _agent_request_package(evidence_package: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    request_package = copy.deepcopy(evidence_package)
    packaging: dict[str, Any] = {
        "mode": "compact_request_package",
        "removed_object_indexes": 0,
        "removed_page_image_indexes": 0,
        "original_source_record_count": _record_count(evidence_package),
        "sent_source_record_count": _record_count(evidence_package),
        "removed_duplicate_table_cell_records": 0,
        "removed_table_aggregate_records": 0,
        "removed_duplicate_row_text_values": 0,
        "record_encoding": "compact_ref_loc_text",
    }

    for side in ("source", "template"):
        side_payload = request_package.get(side)
        if not isinstance(side_payload, dict):
            continue
        if side_payload.pop("page_image_index", None) is not None:
            packaging["removed_page_image_indexes"] += 1
        structured = side_payload.get("structured")
        if isinstance(structured, dict) and structured.pop("object_index", None) is not None:
            packaging["removed_object_indexes"] += 1

    source_structured = request_package.get("source", {}).get("structured", {})
    if isinstance(source_structured, dict):
        records, record_stats = _compact_source_records(source_structured.get("records"))
        source_structured["records"] = records
        packaging.update(record_stats)
        packaging["sent_source_record_count"] = len(records)

    return request_package, packaging


def _record_count(evidence_package: dict[str, Any]) -> int:
    records = evidence_package.get("source", {}).get("structured", {}).get("records", [])
    return len(records) if isinstance(records, list) else 0


def _compact_source_records(raw_records: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not isinstance(raw_records, list):
        return [], {
            "removed_duplicate_table_cell_records": 0,
            "removed_table_aggregate_records": 0,
            "removed_duplicate_row_text_values": 0,
        }

    row_locations = {
        _table_row_key(record)
        for record in raw_records
        if isinstance(record, dict) and _is_table_row_record(_record_id(record))
    }
    row_locations.discard((None, None))

    compact_records: list[dict[str, Any]] = []
    removed_duplicate_cells = 0
    removed_table_aggregates = 0
    removed_row_text_values = 0
    for record in raw_records:
        if not isinstance(record, dict):
            continue
        record_id = _record_id(record)
        if not record_id:
            continue
        if _is_table_cell_record(record_id) and _table_row_key(record) in row_locations:
            removed_duplicate_cells += 1
            continue
        if _is_table_aggregate_record(record_id):
            removed_table_aggregates += 1
            continue

        text, removed_row_text = _record_text(record)
        removed_row_text_values += removed_row_text
        if not text:
            continue
        compact_record = {
            "ref": f"record:{record_id}",
            "text": text,
        }
        location = _location_text(record.get("locator"))
        if location:
            compact_record["loc"] = location
        compact_records.append(compact_record)

    return compact_records, {
        "removed_duplicate_table_cell_records": removed_duplicate_cells,
        "removed_table_aggregate_records": removed_table_aggregates,
        "removed_duplicate_row_text_values": removed_row_text_values,
    }


def _record_id(record: dict[str, Any]) -> str:
    value = record.get("record_id")
    return value if isinstance(value, str) else ""


def _is_table_row_record(record_id: str) -> bool:
    return record_id.startswith("tblrow")


def _is_table_cell_record(record_id: str) -> bool:
    return record_id.startswith("tblcell")


def _is_table_aggregate_record(record_id: str) -> bool:
    return record_id.startswith("tbl_")


def _table_row_key(record: dict[str, Any]) -> tuple[Any, Any]:
    locator = record.get("locator") if isinstance(record.get("locator"), dict) else {}
    return record.get("table_id") or locator.get("table_id"), locator.get("row_index")


def _record_text(record: dict[str, Any]) -> tuple[str, int]:
    values = record.get("values", [])
    if not isinstance(values, list):
        return "", 0

    parts: list[str] = []
    removed_row_text = 0
    has_structured_values = any(
        isinstance(value, dict)
        and value.get("canonical_key") not in ("row_text", "table_text")
        and value.get("value") not in (None, "", [], {})
        for value in values
    )
    for value in values:
        if not isinstance(value, dict):
            continue
        key = value.get("canonical_key")
        raw_value = value.get("value")
        if raw_value in (None, "", [], {}):
            continue
        if key in ("row_text", "table_text") and has_structured_values:
            removed_row_text += 1
            continue
        text_value = str(raw_value)
        if isinstance(key, str) and key and key != text_value:
            parts.append(f"{key}={text_value}")
        else:
            parts.append(text_value)
    return " | ".join(parts), removed_row_text


def _location_text(locator: Any) -> str:
    if not isinstance(locator, dict):
        return ""
    parts: list[str] = []
    for key in ("page_anchor", "section_title", "table_title", "table_id", "row_index", "column_index"):
        value = locator.get(key)
        if value not in (None, "", [], {}):
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def _finalize_user_prompt(
    evidence_package: dict[str, Any],
    *,
    agent_input: dict[str, Any],
    system_prompt: str,
    user_parts: list[dict[str, Any]],
    use_default_provider_limit: bool,
) -> str:
    user_prompt = ""
    for _ in range(3):
        user_prompt = "INPUT_JSON:\n" + json.dumps(
            {"evidence_package": evidence_package},
            ensure_ascii=False,
            sort_keys=True,
        )
        user_parts[0]["text"] = user_prompt
        previous_estimates = (
            agent_input.get("estimated_request_bytes"),
            agent_input.get("estimated_input_chars"),
        )
        _record_payload_estimates(
            agent_input,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            user_parts=user_parts,
            use_default_provider_limit=use_default_provider_limit,
        )
        current_estimates = (
            agent_input.get("estimated_request_bytes"),
            agent_input.get("estimated_input_chars"),
        )
        if previous_estimates == current_estimates:
            break
    user_prompt = "INPUT_JSON:\n" + json.dumps(
        {"evidence_package": evidence_package},
        ensure_ascii=False,
        sort_keys=True,
    )
    user_parts[0]["text"] = user_prompt
    return user_prompt


def _inline_page_images(evidence_package: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inline_images: list[dict[str, Any]] = []
    skipped_page_images: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "max_inline_page_images": _max_inline_page_images(),
        "max_inline_image_chars": _max_inline_image_chars(),
        "max_inline_image_total_chars": _max_inline_image_total_chars(),
    }
    candidate_page_images = _candidate_page_images(evidence_package)
    per_image_limit = _per_image_char_limit(len(candidate_page_images))
    encoded_total_chars = 0
    for page_image in candidate_page_images:
        if _inline_page_image_limit_reached(summary, inline_images):
            skipped_page_images.append(_page_image_summary(page_image, reason="inline_page_image_limit"))
            continue
        data_url = _image_data_url(page_image.get("image_ref"), max_encoded_chars=per_image_limit)
        if data_url is None:
            skipped_page_images.append(_page_image_summary(page_image, reason="image_not_inlineable"))
            continue
        if _inline_image_total_limit_reached(summary, encoded_total_chars, len(data_url)):
            skipped_page_images.append(_page_image_summary(page_image, reason="inline_image_total_char_limit"))
            continue
        image_summary = _page_image_summary(page_image)
        image_summary["encoded_chars"] = len(data_url)
        inline_images.append(
            {
                "part": {"type": "image_url", "image_url": {"url": data_url}},
                "summary": image_summary,
            }
        )
        encoded_total_chars += len(data_url)
    return inline_images, skipped_page_images


def _user_parts(
    evidence_package: dict[str, Any],
    *,
    inline_images: list[dict[str, Any]],
    skipped_page_images: list[dict[str, Any]],
    client_accepts_user_parts: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": ""}]
    parts.extend(item["part"] for item in inline_images)
    sent_page_images = [dict(item["summary"]) for item in inline_images]
    summary: dict[str, Any] = {
        "max_inline_page_images": _max_inline_page_images(),
        "max_inline_image_chars": _max_inline_image_chars(),
        "max_inline_image_total_chars": _max_inline_image_total_chars(),
        "adaptive_inline_image_chars": _per_image_char_limit(len(_candidate_page_images(evidence_package))),
        "client_accepts_user_parts": client_accepts_user_parts,
        "sent_page_images": sent_page_images,
        "skipped_page_images": list(skipped_page_images),
        "inline_page_image_count": len(sent_page_images),
        "delivered_inline_page_image_count": len(sent_page_images) if client_accepts_user_parts else 0,
        "skipped_page_image_count": len(skipped_page_images),
        "inline_page_image_total_chars": sum(
            int(item.get("encoded_chars", 0))
            for item in sent_page_images
            if isinstance(item.get("encoded_chars", 0), int)
        ),
    }
    if not client_accepts_user_parts and sent_page_images:
        summary["delivery_warning"] = "agent_visual_input_not_supported_by_client"
    return parts, summary


def _record_payload_estimates(
    agent_input: dict[str, Any],
    *,
    system_prompt: str,
    user_prompt: str,
    user_parts: list[dict[str, Any]],
    use_default_provider_limit: bool,
) -> None:
    max_request_body_bytes = resolve_llm_request_body_limit_bytes()
    max_input_chars = _provider_input_char_limit(use_default_provider_limit=use_default_provider_limit)
    estimated_request_bytes = estimate_chat_request_bytes(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        user_parts=user_parts,
    )
    estimated_input_chars = estimate_chat_input_chars(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        user_parts=user_parts,
    )
    agent_input["estimated_request_bytes"] = estimated_request_bytes
    agent_input["max_request_body_bytes"] = max_request_body_bytes
    agent_input["request_body_within_limit"] = (
        max_request_body_bytes is None
        or estimated_request_bytes <= max_request_body_bytes
    )
    agent_input["estimated_input_chars"] = estimated_input_chars
    agent_input["max_input_chars"] = max_input_chars
    agent_input["input_chars_within_limit"] = (
        max_input_chars is None
        or estimated_input_chars <= max_input_chars
    )
    agent_input["preflight_blocked"] = False


def _payload_over_limit_reason(agent_input: dict[str, Any]) -> str | None:
    if not agent_input.get("input_chars_within_limit", True):
        return "provider_input_char_budget"
    if not agent_input.get("request_body_within_limit", True):
        return "request_body_budget"
    return None


def _raise_payload_too_large(agent_input: dict[str, Any], reason: str) -> None:
    agent_input["preflight_blocked"] = True
    agent_input["preflight_blocked_reason"] = reason
    if reason == "provider_input_char_budget":
        raise DoctransaiLLMInputTooLargeError(
            estimated_input_chars=int(agent_input["estimated_input_chars"]),
            max_input_chars=int(agent_input["max_input_chars"]),
        )
    raise DoctransaiLLMRequestTooLargeError(
        estimated_request_bytes=int(agent_input["estimated_request_bytes"]),
        max_request_body_bytes=int(agent_input["max_request_body_bytes"]),
    )


def _skipped_inline_image_summary(inline_image: dict[str, Any], *, reason: str) -> dict[str, Any]:
    summary = dict(inline_image["summary"])
    summary["reason"] = reason
    return summary


def _candidate_page_images(evidence_package: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *_page_images_for_side(evidence_package, "template"),
        *_page_images_for_side(evidence_package, "source"),
    ]


def _page_images_for_side(evidence_package: dict[str, Any], side: str) -> list[dict[str, Any]]:
    raw_items = evidence_package.get(side, {}).get("page_images", [])
    if not isinstance(raw_items, list):
        return []
    return [{**item, "side": side} for item in raw_items if isinstance(item, dict)]


def _inline_page_image_limit_reached(summary: dict[str, Any], inline_images: list[dict[str, Any]]) -> bool:
    max_images = summary["max_inline_page_images"]
    return isinstance(max_images, int) and max_images > 0 and len(inline_images) >= max_images


def _inline_image_total_limit_reached(
    summary: dict[str, Any],
    current_encoded_chars: int,
    next_encoded_chars: int,
) -> bool:
    max_chars = summary["max_inline_image_total_chars"]
    return isinstance(max_chars, int) and max_chars > 0 and current_encoded_chars + next_encoded_chars > max_chars


def _page_image_summary(page_image: dict[str, Any], *, reason: str | None = None) -> dict[str, Any]:
    summary = {
        "side": page_image.get("side"),
        "page_index": page_image.get("page_index"),
        "image_ref": page_image.get("image_ref"),
    }
    if reason is not None:
        summary["reason"] = reason
    return summary


def _max_inline_page_images() -> int:
    return _env_int(DOCTRANSAI_AGENTIC_MAX_INLINE_PAGE_IMAGES_ENV, DEFAULT_MAX_INLINE_PAGE_IMAGES)


def _max_inline_image_chars() -> int:
    return _env_int(DOCTRANSAI_AGENTIC_MAX_INLINE_IMAGE_CHARS_ENV, DEFAULT_MAX_INLINE_IMAGE_CHARS)


def _max_inline_image_total_chars() -> int:
    return _env_int(DOCTRANSAI_AGENTIC_MAX_INLINE_IMAGE_TOTAL_CHARS_ENV, DEFAULT_MAX_INLINE_IMAGE_TOTAL_CHARS)


def _provider_input_char_limit(*, use_default_provider_limit: bool) -> int | None:
    configured = os.environ.get(DOCTRANSAI_AGENTIC_PROVIDER_MAX_INPUT_CHARS_ENV)
    if configured is not None:
        value = _env_int(DOCTRANSAI_AGENTIC_PROVIDER_MAX_INPUT_CHARS_ENV, DEFAULT_AGENTIC_PROVIDER_MAX_INPUT_CHARS)
        return value if value > 0 else None
    resolved = resolve_llm_input_char_limit()
    if resolved is not None:
        return resolved
    return DEFAULT_AGENTIC_PROVIDER_MAX_INPUT_CHARS if use_default_provider_limit else None


def _per_image_char_limit(page_image_count: int) -> int:
    max_per_image = _max_inline_image_chars()
    total_limit = _max_inline_image_total_chars()
    if page_image_count <= 0 or total_limit <= 0:
        return max_per_image
    return max(4_000, min(max_per_image, total_limit // page_image_count))


def _env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _image_data_url(image_ref: Any, *, max_encoded_chars: int | None = None) -> str | None:
    if not image_ref:
        return None
    path = Path(str(image_ref)).expanduser()
    if not path.exists() or not path.is_file():
        return None
    limit = max_encoded_chars if max_encoded_chars is not None else _max_inline_image_chars()
    image_bytes, mime_type = _compressed_image_bytes(path, max_encoded_chars=limit)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    if len(encoded) > limit:
        return None
    return f"data:{mime_type};base64,{encoded}"


def _compressed_image_bytes(path: Path, *, max_encoded_chars: int) -> tuple[bytes, str]:
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            for max_side in (1400, 1100, 900, 700, 500, 360, 280, 220, 180):
                resized = image.copy()
                resized.thumbnail((max_side, max_side))
                for quality in (85, 75, 65, 55, 40, 30):
                    buffer = BytesIO()
                    resized.save(buffer, format="JPEG", quality=quality, optimize=True)
                    payload = buffer.getvalue()
                    if len(base64.b64encode(payload)) <= max_encoded_chars:
                        return payload, "image/jpeg"
    except Exception:  # noqa: BLE001
        pass

    return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "image/png"
