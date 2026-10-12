from __future__ import annotations

import re
from typing import Any, Iterable

from doctransai.mapping.type_inference import infer_slot_value_type, infer_source_value_type
from doctransai.models.mapping import FieldCandidate
from doctransai.models.source import ProvenanceRef, SourceModel, SourceRecord, SourceValue
from doctransai.models.template import TemplateSlot


_TEXT_FACT_KEYS = {"text", "table_text", "range_text", "sheet_summary"}


def build_text_candidates_for_slot(
    *,
    slot: TemplateSlot,
    primary_record: SourceRecord,
    source_model: SourceModel,
) -> list[FieldCandidate]:
    slot_label = _normalize_label(slot.raw_name or slot.canonical_name)
    expected_type = infer_slot_value_type(slot)
    candidates: list[FieldCandidate] = []

    candidates.extend(
        _direct_value_candidates(
            slot=slot,
            slot_label=slot_label,
            expected_type=expected_type,
            record=primary_record,
            relation="same_record_row",
        )
    )

    candidates.extend(
        _fact_candidates(
            slot=slot,
            slot_label=slot_label,
            expected_type=expected_type,
            record=primary_record,
            relation="same_record_row",
        )
    )

    if not candidates and expected_type != "text":
        candidates.extend(
            _same_row_unique_typed_candidates(
                slot=slot,
                expected_type=expected_type,
                record=primary_record,
            )
        )

    for record in source_model.records:
        if record.record_id == primary_record.record_id:
            continue
        relation = "table_context" if record.table_id and record.table_id == primary_record.table_id else "text_fact"
        candidates.extend(
            _fact_candidates(
                slot=slot,
                slot_label=slot_label,
                expected_type=expected_type,
                record=record,
                relation=relation,
            )
        )

    return _dedupe_candidates(candidates)


def build_label_echo_filtered_candidates_for_slot(
    *,
    slot: TemplateSlot,
    primary_record: SourceRecord,
) -> list[FieldCandidate]:
    slot_label = _normalize_label(slot.raw_name or slot.canonical_name)
    expected_type = infer_slot_value_type(slot)
    return _dedupe_candidates(
        _label_echo_filtered_candidates(
            slot=slot,
            slot_label=slot_label,
            expected_type=expected_type,
            record=primary_record,
        )
    )


def _direct_value_candidates(
    *,
    slot: TemplateSlot,
    slot_label: str,
    expected_type: str,
    record: SourceRecord,
    relation: str,
) -> list[FieldCandidate]:
    candidates: list[FieldCandidate] = []
    for index, value in enumerate(record.values):
        label = value.raw_label or value.canonical_key
        normalized_label = _normalize_label(label)
        value_type = infer_source_value_type(value)
        if expected_type not in {"text", value_type}:
            continue
        if _is_label_echo(value.value, label) or _is_label_echo(value.value, slot.raw_name or slot.canonical_name):
            continue

        if normalized_label == slot_label:
            candidates.append(
                FieldCandidate(
                    candidate_id=f"{record.record_id}:{index}:exact_label",
                    slot_id=slot.slot_id,
                    canonical_key=slot.raw_name,
                    value=value.value,
                    confidence=0.99,
                    rule="exact_label",
                    provenance_refs=list(value.provenance),
                    transform=f"{label}->{slot.raw_name}" if label != slot.raw_name else None,
                )
            )
            continue

        if _label_overlap(slot_label, normalized_label) >= 0.6:
            confidence = 0.9 if relation == "same_record_row" else 0.78
            candidates.append(
                FieldCandidate(
                    candidate_id=f"{record.record_id}:{index}:label_overlap",
                    slot_id=slot.slot_id,
                    canonical_key=slot.raw_name,
                    value=value.value,
                    confidence=confidence,
                    rule=relation,
                    provenance_refs=list(value.provenance),
                    transform=f"{label}->{slot.raw_name}",
                )
            )
            continue

        if expected_type != "text" and value_type == expected_type and relation == "same_record_row":
            candidates.append(
                FieldCandidate(
                    candidate_id=f"{record.record_id}:{index}:typed_row_match",
                    slot_id=slot.slot_id,
                    canonical_key=slot.raw_name,
                    value=value.value,
                    confidence=0.78,
                    rule="same_record_row",
                    provenance_refs=list(value.provenance),
                    transform=f"{value_type}_typed_row_match",
                )
            )

    return candidates


def _label_echo_filtered_candidates(
    *,
    slot: TemplateSlot,
    slot_label: str,
    expected_type: str,
    record: SourceRecord,
) -> list[FieldCandidate]:
    candidates: list[FieldCandidate] = []
    raw_slot_label = slot.raw_name or slot.canonical_name
    for index, value in enumerate(record.values):
        label = value.raw_label or value.canonical_key
        normalized_label = _normalize_label(label)
        value_type = infer_source_value_type(value)
        if expected_type not in {"text", value_type}:
            continue

        matched_label = None
        if _is_label_echo(value.value, label):
            matched_label = label
        elif _is_label_echo(value.value, raw_slot_label):
            matched_label = raw_slot_label
        if matched_label is None:
            continue
        if (
            normalized_label != slot_label
            and _label_overlap(slot_label, normalized_label) < 0.6
            and not (expected_type != "text" and value_type == expected_type)
        ):
            continue

        candidates.append(
            FieldCandidate(
                candidate_id=f"{record.record_id}:{index}:label_echo_filtered",
                slot_id=slot.slot_id,
                canonical_key=slot.raw_name,
                value=value.value,
                confidence=0.0,
                rule="label_echo_filtered",
                provenance_refs=list(value.provenance),
                transform=f"filtered_label_echo:{matched_label}->{slot.raw_name}",
            )
        )
    return candidates


def _same_row_unique_typed_candidates(
    *,
    slot: TemplateSlot,
    expected_type: str,
    record: SourceRecord,
) -> list[FieldCandidate]:
    typed_values = [
        (index, value)
        for index, value in enumerate(record.values)
        if infer_source_value_type(value) == expected_type and value.value.strip()
    ]
    if expected_type == "text" or len(typed_values) != 1:
        return []

    index, value = typed_values[0]
    return [
        FieldCandidate(
            candidate_id=f"{record.record_id}:{index}:unique_typed_row",
            slot_id=slot.slot_id,
            canonical_key=slot.raw_name,
            value=value.value,
            confidence=0.86,
            rule="same_record_row",
            provenance_refs=list(value.provenance),
            transform=f"unique_{expected_type}_row_value",
        )
    ]


def _fact_candidates(
    *,
    slot: TemplateSlot,
    slot_label: str,
    expected_type: str,
    record: SourceRecord,
    relation: str,
) -> list[FieldCandidate]:
    candidates: list[FieldCandidate] = []
    for value in record.values:
        if value.canonical_key not in _TEXT_FACT_KEYS:
            continue
        for fact_label, fact_value in _extract_named_facts(value.value):
            if not fact_value:
                continue
            normalized_label = _normalize_label(fact_label)
            if normalized_label != slot_label and _label_overlap(slot_label, normalized_label) < 0.6:
                continue
            value_type = infer_source_value_type(SourceValue(canonical_key=fact_label, value=fact_value))
            if expected_type != "text" and value_type != expected_type:
                continue
            if relation == "same_record_row":
                confidence = 0.88
            elif relation == "table_context":
                confidence = 0.82
            else:
                confidence = 0.72
            candidates.append(
                FieldCandidate(
                    candidate_id=f"{record.record_id}:{fact_label}:{relation}",
                    slot_id=slot.slot_id,
                    canonical_key=slot.raw_name,
                    value=fact_value,
                    confidence=confidence,
                    rule=relation,
                    provenance_refs=list(value.provenance),
                    transform=f"{fact_label}->{slot.raw_name}",
                )
            )
    return candidates


def _extract_named_facts(text: str) -> list[tuple[str, str]]:
    facts: list[tuple[str, str]] = []
    for segment in re.split(r"[\n|]", text):
        match = re.match(r"\s*([^:=：]+?)\s*[:=：]\s*(.+?)\s*$", segment)
        if match is None:
            continue
        facts.append((match.group(1).strip(), match.group(2).strip()))
    return facts


def _label_overlap(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union if union else 0.0


def _tokens(value: str) -> Iterable[str]:
    text = value.strip()
    if not text:
        return ()
    if any("\u4e00" <= character <= "\u9fff" for character in text):
        return tuple(character for character in text if not character.isspace() and character != "_")
    return tuple(token for token in re.split(r"[_\W]+", text) if token)


def _normalize_label(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    canonical = re.sub(r"[^\w\u4e00-\u9fff]+", "_", normalized, flags=re.UNICODE).strip("_")
    return canonical.casefold() or normalized.casefold()


def _is_label_echo(value: str, label: str | None) -> bool:
    if not label:
        return False
    return _normalize_label(value) == _normalize_label(label)


def _dedupe_candidates(candidates: list[FieldCandidate]) -> list[FieldCandidate]:
    deduped: list[FieldCandidate] = []
    seen: set[tuple[str, str, tuple[tuple[Any, ...], ...]]] = set()
    for candidate in candidates:
        key = (candidate.rule, candidate.value, _provenance_refs_key(candidate.provenance_refs))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _provenance_refs_key(provenance_refs: list[ProvenanceRef]) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            ref.source_kind,
            ref.document_id,
            ref.evidence_id,
            ref.asset_id,
            ref.object_id,
            _freeze_mapping(ref.locator),
            ref.source_path,
        )
        for ref in provenance_refs
    )


def _freeze_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze_mapping(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_freeze_mapping(item) for item in value)
    return value
