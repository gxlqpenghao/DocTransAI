from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Any

from doctransai.agentic_mapping.decisions import AgentDecision


@dataclass(slots=True)
class ValidationResult:
    accepted_decisions: list[AgentDecision] = field(default_factory=list)
    rejected_decisions: list[AgentDecision] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def validate_agent_decisions(
    decisions: list[AgentDecision],
    evidence_package: dict[str, Any],
) -> ValidationResult:
    source_structured = evidence_package.get("source", {}).get("structured", {})
    source_index = _object_index(evidence_package, "source")
    template_index = _template_index(evidence_package)
    slot_decision_counts = Counter(decision.slot_id for decision in decisions)
    result = ValidationResult()

    for decision in decisions:
        diagnostics = _validate_unique_slot_decision(decision, slot_decision_counts)
        diagnostics.extend(_validate_decision(decision, source_index, template_index, source_structured))
        if diagnostics:
            result.rejected_decisions.append(decision)
            result.diagnostics.extend(diagnostics)
        else:
            result.accepted_decisions.append(decision)

    return result


def _validate_decision(
    decision: AgentDecision,
    source_index: dict[str, Any],
    template_index: dict[str, Any],
    source_structured: dict[str, Any],
) -> list[dict[str, Any]]:
    if decision.decision_type == "unresolved":
        return _validate_unresolved(decision)

    diagnostics: list[dict[str, Any]] = []
    source_ref_diagnostics = _validate_source_refs(decision, source_index, source_structured)
    diagnostics.extend(source_ref_diagnostics)
    diagnostics.extend(_validate_target_ref(decision, template_index))

    if decision.decision_type == "text_fill" and not source_ref_diagnostics:
        diagnostics.extend(_validate_text_value(decision, source_structured, source_index))

    if decision.decision_type == "image_placement":
        diagnostics.extend(_validate_image_asset(decision, source_index, source_structured))

    return diagnostics


def _validate_unique_slot_decision(
    decision: AgentDecision,
    slot_decision_counts: Counter[str],
) -> list[dict[str, Any]]:
    if slot_decision_counts[decision.slot_id] <= 1:
        return []
    return [
        _diagnostic(
            "error",
            "duplicate_slot_decision",
            "Agent returned multiple decisions for the same slot.",
            decision,
            decision_count=slot_decision_counts[decision.slot_id],
        )
    ]


def _validate_text_value(
    decision: AgentDecision,
    source_structured: dict[str, Any],
    source_index: dict[str, Any],
) -> list[dict[str, Any]]:
    value = decision.value or ""
    if not value.strip():
        return [
            _diagnostic(
                "error",
                "missing_text_value",
                "text_fill decisions must include a non-empty value.",
                decision,
            )
        ]
    if _looks_like_label_only(value):
        return [
            _diagnostic(
                "error",
                "label_only_text_value",
                "text_fill value looks like a field label rather than source content.",
                decision,
            )
        ]
    if _reason_contradicts_fill(decision.reason):
        return [
            _diagnostic(
                "error",
                "decision_reason_contradicts_fill",
                "text_fill reason states that source evidence does not support the fill.",
                decision,
            )
        ]
    if not decision.source_refs:
        return []
    if any(
        _source_ref_supports_value(source_structured, source_index, source_ref, value)
        for source_ref in decision.source_refs
    ):
        return []
    if _source_refs_support_generated_text(source_structured, source_index, decision.source_refs, value):
        return []
    repaired_refs = _supporting_record_refs_for_value(source_structured, value)
    if repaired_refs:
        decision.source_refs = list(dict.fromkeys([*decision.source_refs, *repaired_refs]))
        return []
    return [
        _diagnostic(
            "error",
            "text_value_not_supported_by_source_ref",
            "text_fill value was not found in any cited source object.",
            decision,
        )
    ]


def _looks_like_label_only(value: str) -> bool:
    stripped = value.strip()
    return stripped.endswith((":", "：")) and len(stripped) <= 30


def _reason_contradicts_fill(reason: str | None) -> bool:
    if not reason:
        return False
    normalized = reason.casefold()
    negative_markers = (
        "not equivalent",
        "source does not support",
        "source doesn't support",
        "unsupported by source",
        "not supported by source",
        "no source evidence",
        "source has no",
        "source does not contain",
        "source doesn't contain",
        "source does not provide",
        "not a full date",
        "not necessarily",
        "源文档没有",
        "源文档不包含",
        "没有来源证据",
        "不等价",
        "不支持",
    )
    return any(marker in normalized for marker in negative_markers)


def _source_ref_supports_value(
    source_structured: dict[str, Any],
    source_index: dict[str, Any],
    source_ref: str,
    value: str,
) -> bool:
    texts: list[str] = []
    for resolved_ref in _resolve_source_refs(source_index, source_ref):
        texts.extend(_source_ref_texts(source_structured, resolved_ref))
    return any(text and _text_supports_value(text, value) for text in texts)


def _source_refs_support_generated_text(
    source_structured: dict[str, Any],
    source_index: dict[str, Any],
    source_refs: list[str],
    value: str,
) -> bool:
    normalized_value = _claim_text(value)
    if len(normalized_value) < 30:
        return False

    source_texts: list[str] = []
    for source_ref in source_refs:
        for resolved_ref in _resolve_source_refs(source_index, source_ref):
            source_texts.extend(_source_ref_texts(source_structured, resolved_ref))
    normalized_source = _claim_text("\n".join(source_texts))
    if not normalized_source:
        return False

    value_grams = _claim_grams(normalized_value)
    if len(value_grams) < 12:
        return False
    supported_count = sum(1 for gram in value_grams if gram in normalized_source)
    return supported_count / len(value_grams) >= 0.55


def _supporting_record_refs_for_value(source_structured: dict[str, Any], value: str) -> list[str]:
    records = source_structured.get("records", [])
    if not isinstance(records, list):
        return []
    refs: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            continue
        if _text_supports_value(_record_search_text(record), value):
            refs.append(f"record:{record_id}")
    return refs


def _resolve_source_refs(source_index: dict[str, Any], source_ref: str) -> list[str]:
    refs = [source_ref]
    entry = source_index.get(source_ref)
    if isinstance(entry, dict):
        ref = entry.get("ref")
        if isinstance(ref, str) and ref and ref not in refs:
            refs.append(ref)
    return refs


def _text_supports_value(source_text: str, value: str) -> bool:
    stripped_value = value.strip()
    if not stripped_value:
        return False
    if stripped_value in source_text:
        return True
    if _dateish_text_supports_value(source_text, stripped_value):
        return True
    normalized_source = _normalize_list_text(source_text)
    normalized_value = _normalize_list_text(stripped_value)
    if normalized_value in normalized_source:
        return True
    return _text_supports_composed_value(normalized_source, stripped_value)


def _text_supports_composed_value(normalized_source: str, value: str) -> bool:
    fragments = _meaningful_value_fragments(value)
    if len(fragments) < 2:
        return False
    return all(_fragment_supported_by_source(normalized_source, fragment) for fragment in fragments)


def _dateish_text_supports_value(source_text: str, value: str) -> bool:
    normalized_value = _normalize_dateish(value)
    if normalized_value is None:
        return False
    return normalized_value in {
        _normalize_dateish(match.group(0))
        for match in re.finditer(r"\d{4}\s*(?:年|-|/|\.)\s*\d{1,2}(?:\s*(?:月|-|/|\.)\s*\d{1,2}\s*日?)?", source_text)
    }


def _normalize_dateish(value: str) -> str | None:
    match = re.fullmatch(
        r"\s*(\d{4})\s*(?:年|-|/|\.)\s*(\d{1,2})(?:\s*(?:月|-|/|\.)\s*(\d{1,2})\s*日?)?\s*",
        value,
    )
    if match is None:
        return None
    year, month, day = match.groups()
    normalized = f"{int(year):04d}{int(month):02d}"
    if day is not None:
        normalized += f"{int(day):02d}"
    return normalized


def _fragment_supported_by_source(normalized_source: str, fragment: str) -> bool:
    if fragment in normalized_source:
        return True
    if len(fragment) < 8:
        return False
    return _has_near_substring(normalized_source, fragment, max_distance=1)


def _has_near_substring(normalized_source: str, fragment: str, *, max_distance: int) -> bool:
    source_length = len(normalized_source)
    fragment_length = len(fragment)
    for window_length in range(max(1, fragment_length - max_distance), fragment_length + max_distance + 1):
        if window_length > source_length:
            continue
        for start in range(0, source_length - window_length + 1):
            if _edit_distance_within(fragment, normalized_source[start : start + window_length], max_distance):
                return True
    return False


def _edit_distance_within(left: str, right: str, max_distance: int) -> bool:
    if abs(len(left) - len(right)) > max_distance:
        return False

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            substitution_cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + substitution_cost,
                )
            )
            row_min = min(row_min, current[-1])
        if row_min > max_distance:
            return False
        previous = current
    return previous[-1] <= max_distance


def _meaningful_value_fragments(value: str) -> list[str]:
    fragments: list[str] = []
    for part in re.split(r"[；;、,，\n\r]+", value):
        fragment = _normalize_list_text(part)
        fragment = re.sub(r"^[一二三四五六七八九十\d]+[.．、]", "", fragment)
        if len(fragment) >= 2:
            fragments.append(fragment)
    return fragments


def _normalize_list_text(text: str) -> str:
    normalized = re.sub(r"[（(][一二三四五六七八九十\d]+[）)]", "", text)
    return re.sub(r"\s+", "", normalized)


def _claim_text(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text)


def _claim_grams(normalized_text: str, *, width: int = 3) -> set[str]:
    return {
        normalized_text[index : index + width]
        for index in range(0, max(0, len(normalized_text) - width + 1))
        if len(normalized_text[index : index + width]) == width
    }


def _source_ref_texts(source_structured: dict[str, Any], source_ref: str) -> list[str]:
    if source_ref.startswith("source_value:"):
        parts = source_ref.split(":", 2)
        if len(parts) != 3:
            return []
        record_id = parts[1]
        try:
            index_or_column = int(parts[2])
        except ValueError:
            return []
        record = _record_by_id(source_structured, record_id)
        return _source_value_texts(record, index_or_column)
    if source_ref.startswith("record:"):
        record = _record_by_id(source_structured, source_ref.removeprefix("record:"))
        return [_record_search_text(record)]
    return []


def _source_value_texts(record: dict[str, Any], index_or_column: int) -> list[str]:
    values = record.get("values", []) if isinstance(record, dict) else []
    if not isinstance(values, list):
        return []

    texts: list[str] = []
    if 0 <= index_or_column < len(values) and isinstance(values[index_or_column], dict):
        _append_text(texts, values[index_or_column].get("value"))

    # Agents may cite spreadsheet cells by either the one-based locator column
    # index or a zero-based column position; both are stable factual refs.
    for value in values:
        if not isinstance(value, dict):
            continue
        if _value_column_index(value) in {index_or_column, index_or_column + 1}:
            _append_text(texts, value.get("value"))
    return list(dict.fromkeys(texts))


def _value_column_index(value: dict[str, Any]) -> int | None:
    provenance_items = value.get("provenance", [])
    if not isinstance(provenance_items, list):
        return None
    for provenance in provenance_items:
        if not isinstance(provenance, dict):
            continue
        locator = provenance.get("locator")
        if not isinstance(locator, dict):
            continue
        column_index = locator.get("column_index")
        if isinstance(column_index, int):
            return column_index
    return None


def _record_search_text(record: dict[str, Any]) -> str:
    if not isinstance(record, dict):
        return ""
    fragments: list[str] = []
    values = record.get("values", [])
    if isinstance(values, list):
        for value in values:
            if not isinstance(value, dict):
                continue
            _append_text(fragments, value.get("value"))
            provenance_items = value.get("provenance", [])
            if isinstance(provenance_items, list):
                for provenance in provenance_items:
                    if isinstance(provenance, dict):
                        _append_locator_text(fragments, provenance.get("locator"))
    _append_locator_text(fragments, record.get("locator"))
    return "\n".join(fragments)


def _append_locator_text(fragments: list[str], locator: Any) -> None:
    if not isinstance(locator, dict):
        return
    for value in locator.values():
        _append_text(fragments, value)


def _append_text(fragments: list[str], value: Any) -> None:
    if isinstance(value, str) and value:
        fragments.append(value)


def _record_by_id(source_structured: dict[str, Any], record_id: str) -> dict[str, Any]:
    records = source_structured.get("records", [])
    if not isinstance(records, list):
        return {}
    return next(
        (
            record
            for record in records
            if isinstance(record, dict) and record.get("record_id") == record_id
        ),
        {},
    )


def _validate_unresolved(decision: AgentDecision) -> list[dict[str, Any]]:
    if decision.reason:
        return []
    return [
        _diagnostic(
            "error",
            "missing_reason",
            "Unresolved decisions must include a reason.",
            decision,
        )
    ]


def _validate_source_refs(
    decision: AgentDecision,
    source_index: dict[str, Any],
    source_structured: dict[str, Any],
) -> list[dict[str, Any]]:
    if not decision.source_refs:
        return [
            _diagnostic(
                "error",
                "missing_source_refs",
                f"{decision.decision_type} decisions must include at least one source ref.",
                decision,
            )
        ]

    diagnostics: list[dict[str, Any]] = []
    for source_ref in decision.source_refs:
        if source_ref not in source_index and not _source_ref_resolves(source_structured, source_ref):
            diagnostics.append(
                _diagnostic(
                    "error",
                    "source_ref_not_found",
                    f"Source ref '{source_ref}' does not exist in source structured object_index.",
                    decision,
                    source_ref=source_ref,
                )
            )
    return diagnostics


def _source_ref_resolves(source_structured: dict[str, Any], source_ref: str) -> bool:
    return bool(_source_ref_texts(source_structured, source_ref))


def _validate_target_ref(
    decision: AgentDecision,
    template_index: dict[str, Any],
) -> list[dict[str, Any]]:
    if _is_visual_target_ref(decision.target_ref):
        return []

    target_key = _target_object_key(decision.target_ref)
    if not target_key:
        inferred_target_key = f"template_slot:{decision.slot_id}"
        if inferred_target_key in template_index:
            return []
        return [
            _diagnostic(
                "error",
                "missing_target_ref",
                f"{decision.decision_type} decisions must include a target_ref when slot_id is not a known template slot.",
                decision,
            )
        ]
    if f"template_slot:{target_key}" in template_index:
        return []
    if target_key not in template_index:
        return [
            _diagnostic(
                "error",
                "target_ref_not_found",
                f"Target ref '{target_key}' does not exist in template structured object_index.",
                decision,
                target_ref=target_key,
            )
        ]
    return []


def _is_visual_target_ref(target_ref: str | dict[str, Any] | None) -> bool:
    if not isinstance(target_ref, dict):
        return False
    if target_ref.get("target_kind") != "visual_text_anchor":
        return False
    return any(
        isinstance(target_ref.get(key), str) and target_ref.get(key)
        for key in ("label_or_nearby_text", "nearby_text", "notes")
    ) or isinstance(target_ref.get("bbox"), list)


def _validate_image_asset(
    decision: AgentDecision,
    source_index: dict[str, Any],
    source_structured: dict[str, Any],
) -> list[dict[str, Any]]:
    if not decision.asset_ref:
        return [
            _diagnostic(
                "error",
                "missing_asset_ref",
                "image_placement decisions must include an asset_ref.",
                decision,
            )
        ]

    asset_key = (
        decision.asset_ref
        if decision.asset_ref.startswith("image_asset:")
        else f"image_asset:{decision.asset_ref}"
    )
    if asset_key not in source_index:
        return [
            _diagnostic(
                "error",
                "image_asset_not_found",
                f"Image asset '{decision.asset_ref}' does not exist in source structured object_index.",
                decision,
                asset_ref=decision.asset_ref,
            )
        ]
    diagnostics: list[dict[str, Any]] = []
    image_asset_refs = [ref for ref in decision.source_refs if ref.startswith("image_asset:")]
    if image_asset_refs and asset_key not in image_asset_refs:
        diagnostics.append(
            _diagnostic(
                "error",
                "image_asset_source_ref_mismatch",
                "image_placement asset_ref must match any image_asset source_refs.",
                decision,
                asset_ref=decision.asset_ref,
                image_asset_refs=image_asset_refs,
            )
        )

    asset_entry = source_index.get(asset_key, {})
    full_asset_entry = _image_asset_by_id(source_structured, decision.asset_ref)
    if decision.source_ref and isinstance(asset_entry, dict):
        allowed_refs = {
            value
            for value in (
                asset_entry.get("source_ref"),
                asset_entry.get("asset_path"),
                full_asset_entry.get("source_ref"),
                full_asset_entry.get("asset_path"),
            )
            if isinstance(value, str) and value
        }
        if allowed_refs and decision.source_ref not in allowed_refs:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "image_source_ref_mismatch",
                    "image_placement source_ref must match the selected image asset.",
                    decision,
                    asset_ref=decision.asset_ref,
                    source_ref=decision.source_ref,
                )
            )
    return diagnostics


def _image_asset_by_id(source_structured: dict[str, Any], asset_id: str | None) -> dict[str, Any]:
    if not asset_id:
        return {}
    image_assets = source_structured.get("image_assets", [])
    if not isinstance(image_assets, list):
        return {}
    return next(
        (
            asset
            for asset in image_assets
            if isinstance(asset, dict) and asset.get("asset_id") == asset_id
        ),
        {},
    )


def _object_index(evidence_package: dict[str, Any], side: str) -> dict[str, Any]:
    structured = evidence_package.get(side, {}).get("structured", {})
    object_index = structured.get("object_index", {})
    if isinstance(object_index, dict):
        return object_index
    return {}


def _template_index(evidence_package: dict[str, Any]) -> dict[str, Any]:
    index = dict(_object_index(evidence_package, "template"))
    targets = evidence_package.get("template", {}).get("targets", [])
    if not isinstance(targets, list):
        return index
    for target in targets:
        if not isinstance(target, dict):
            continue
        target_id = target.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            continue
        entry = {
            "object_type": "template_target",
            "target_id": target_id,
            "origin": target.get("origin"),
            "target_kind": target.get("target_kind"),
        }
        index.setdefault(target_id, entry)
        index.setdefault(f"template_target:{target_id}", entry)
    return index


def _target_object_key(target_ref: str | dict[str, Any] | None) -> str | None:
    if isinstance(target_ref, str):
        return target_ref
    if not isinstance(target_ref, dict):
        return None

    for key in ("object_ref", "target_ref", "ref"):
        value = target_ref.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _diagnostic(
    severity: str,
    code: str,
    message: str,
    decision: AgentDecision,
    **extra: Any,
) -> dict[str, Any]:
    diagnostic = {
        "severity": severity,
        "code": code,
        "message": message,
        "slot_id": decision.slot_id,
    }
    diagnostic.update(extra)
    return diagnostic


__all__ = ["ValidationResult", "validate_agent_decisions"]
