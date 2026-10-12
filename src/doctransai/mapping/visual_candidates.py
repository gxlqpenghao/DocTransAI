from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from doctransai.models.mapping import ImageCandidate, UnresolvedSlot
from doctransai.models.render_plan import PlanDiagnostic
from doctransai.models.source import ProvenanceRef, SourceImageAsset, SourceModel, SourceRecord
from doctransai.models.template import TemplateSlot


_IMAGE_LABEL_TOKENS = ("照片", "图片", "图像", "photo", "image", "img", "picture", "pic")
_DESCRIPTION_LABEL_TOKENS = ("描述", "说明", "内容", "结果", "caption", "remark", "description")
_GENERIC_IMAGE_TEXTS = {"picture", "picture 1", "image", "image 1", "图片", "照片"}


@dataclass(slots=True)
class ImageCandidateResult:
    candidates: list[ImageCandidate] = field(default_factory=list)
    unresolved_slots: list[UnresolvedSlot] = field(default_factory=list)
    diagnostics: list[PlanDiagnostic] = field(default_factory=list)


@dataclass(slots=True)
class ImageAvailability:
    candidate: ImageCandidate
    asset: SourceImageAsset


@dataclass(slots=True)
class VisualContentUnit:
    asset: SourceImageAsset
    relation: str
    confidence: float
    description_text: str | None = None


def build_image_candidates_for_slot(
    *,
    source_model: SourceModel,
    record: SourceRecord,
    slot: TemplateSlot,
) -> ImageCandidateResult:
    if slot.slot_kind != "image":
        return ImageCandidateResult()

    header_by_sheet = build_image_header_index(source_model.records)
    availability = build_image_availability_for_slot(
        slot=slot,
        primary_record=record,
        source_model=source_model,
        header_by_sheet=header_by_sheet,
    )
    candidates: list[ImageCandidate] = []
    missing_assets: list[ImageAvailability] = []
    for item in availability:
        if _asset_file_exists(item.asset):
            candidates.append(item.candidate)
        else:
            missing_assets.append(item)

    candidates.sort(key=lambda candidate: (-candidate.confidence, candidate.asset_id))
    if candidates or not missing_assets:
        return ImageCandidateResult(candidates=candidates)

    first_missing = missing_assets[0]
    role = first_missing.candidate.placement_role or slot.raw_name
    return ImageCandidateResult(
        unresolved_slots=[
            UnresolvedSlot(
                slot_id=slot.slot_id,
                canonical_key=slot.canonical_name,
                reason_code="missing_image_asset_file",
                message=f"Matched image file is missing for {role}: {first_missing.asset.asset_id}",
                provenance_refs=list(first_missing.candidate.provenance_refs),
            )
        ],
        diagnostics=[
            PlanDiagnostic(
                severity="warning",
                code="missing_image_asset_file",
                message=f"Matched image file is missing for {role}: {first_missing.asset.asset_id}",
                field=slot.slot_id,
            )
        ],
    )


def build_image_availability_for_slot(
    *,
    slot: TemplateSlot,
    primary_record: SourceRecord,
    source_model: SourceModel,
    header_by_sheet: dict[str, dict[int, str]] | None = None,
) -> list[ImageAvailability]:
    slot_key = _slot_role_key(slot)
    row_index = _row_index(primary_record)
    sheet_name = _optional_string(primary_record.locator.get("sheet_name"))
    headers = header_by_sheet or build_image_header_index(source_model.records)
    availability: list[ImageAvailability] = []

    for asset in source_model.image_assets:
        if sheet_name is not None and asset.sheet_name != sheet_name:
            continue

        header_name = headers.get(asset.sheet_name or "", {}).get(asset.column_index or -1)
        header_key = _normalize(header_name) if header_name else ""

        rule: str | None = None
        confidence = 0.0
        if row_index is not None and asset.row_index == row_index and header_key and header_key == slot_key:
            rule = "exact_label"
            confidence = 0.99
        elif row_index is not None and asset.row_index == row_index:
            rule = "same_record_row"
            confidence = 0.70 if primary_record.evidence_id and primary_record.evidence_id in asset.related_evidence_ids else 0.65
        elif primary_record.evidence_id and primary_record.evidence_id in asset.related_evidence_ids:
            rule = "weak_context"
            confidence = 0.55

        if rule is None:
            continue

        availability.append(
            ImageAvailability(
                candidate=ImageCandidate(
                    candidate_id=asset.asset_id,
                    slot_id=slot.slot_id,
                    asset_id=asset.asset_id,
                    source_ref=asset.source_ref,
                    confidence=confidence,
                    rule=rule,
                    provenance_refs=[_asset_provenance(asset, primary_record, header_name=header_name)],
                    placement_role=header_name,
                ),
                asset=asset,
            )
        )

    exact_matches = [item for item in availability if item.candidate.rule == "exact_label"]
    return exact_matches or availability


def build_visual_content_units_for_primary_record(
    *,
    source_model: SourceModel,
    primary_record: SourceRecord,
) -> list[VisualContentUnit]:
    primary_sheet_name = primary_record.locator.get("sheet_name")
    primary_row_index = _row_index(primary_record)
    primary_evidence_id = primary_record.evidence_id
    header_by_sheet = build_image_header_index(source_model.records)
    units: list[VisualContentUnit] = []

    for asset in source_model.image_assets:
        relation: str | None = None
        confidence = 0.0
        if (
            primary_sheet_name is not None
            and primary_row_index is not None
            and asset.sheet_name == primary_sheet_name
            and asset.row_index == primary_row_index
        ):
            relation = "same_record_row"
            confidence = 0.95
        elif primary_evidence_id and primary_evidence_id in {*asset.nearby_evidence_ids, *asset.related_evidence_ids}:
            relation = "near_primary_record_context"
            confidence = 0.86
        elif asset.document_id == primary_record.document_id:
            relation = "document_context"
            confidence = 0.45

        if relation is None:
            continue
        units.append(
            VisualContentUnit(
                asset=asset,
                relation=relation,
                confidence=confidence,
                description_text=_visual_unit_description(
                    asset,
                    primary_record=primary_record,
                    header_by_sheet=header_by_sheet,
                ),
            )
        )

    relation_priority = {"same_record_row": 0, "near_primary_record_context": 1, "document_context": 2}
    units.sort(
        key=lambda unit: (
            relation_priority.get(unit.relation, 99),
            unit.asset.order_index if unit.asset.order_index is not None else 10**9,
            unit.asset.asset_id,
        )
    )
    return units


def build_image_header_index(records: list[SourceRecord]) -> dict[str, dict[int, str]]:
    indexed: dict[str, dict[int, tuple[int, str]]] = {}
    for record in records:
        sheet_name = _optional_string(record.locator.get("sheet_name"))
        row_index = _row_index(record)
        if sheet_name is None or row_index is None:
            continue
        for value in record.values:
            for ref in value.provenance:
                column_index = ref.locator.get("column_index")
                if not isinstance(column_index, int):
                    continue
                existing = indexed.setdefault(sheet_name, {}).get(column_index)
                if existing is None or row_index < existing[0]:
                    indexed[sheet_name][column_index] = (row_index, value.canonical_key)

        parser_signals = record.raw.get("parser_signals")
        if isinstance(parser_signals, dict):
            header_values = parser_signals.get("header_values")
            if isinstance(header_values, list):
                for column_index, header in enumerate(header_values, start=1):
                    text = str(header).strip()
                    if not text:
                        continue
                    existing = indexed.setdefault(sheet_name, {}).get(column_index)
                    if existing is None or row_index < existing[0]:
                        indexed[sheet_name][column_index] = (row_index, text)

    return {
        sheet_name: {column_index: name for column_index, (_, name) in columns.items()}
        for sheet_name, columns in indexed.items()
    }


def _slot_role_key(slot: TemplateSlot) -> str:
    header_name = slot.placement_constraints.get("header_name")
    if isinstance(header_name, str) and header_name.strip():
        return _normalize(header_name)
    return _normalize(slot.raw_name or slot.canonical_name)


def _asset_file_exists(asset: SourceImageAsset) -> bool:
    if asset.asset_path:
        return Path(asset.asset_path).expanduser().is_file()
    return False


def _asset_provenance(
    asset: SourceImageAsset,
    primary_record: SourceRecord,
    *,
    header_name: str | None,
) -> ProvenanceRef:
    locator: dict[str, object] = {}
    if asset.sheet_name is not None:
        locator["sheet_name"] = asset.sheet_name
    if asset.row_index is not None:
        locator["row_index"] = asset.row_index
    if asset.column_index is not None:
        locator["column_index"] = asset.column_index
    if asset.cell_anchor is not None:
        locator["cell_anchor"] = asset.cell_anchor
    if header_name is not None:
        locator["header_name"] = header_name

    return ProvenanceRef(
        source_kind="asset",
        document_id=_optional_string(asset.raw.get("document_id")) or primary_record.document_id,
        asset_id=asset.asset_id,
        object_id=asset.asset_id,
        locator=locator,
        source_path=_optional_string(asset.raw.get("source_path")) or asset.source_path or primary_record.source_path,
    )


def _visual_unit_description(
    asset: SourceImageAsset,
    *,
    primary_record: SourceRecord,
    header_by_sheet: dict[str, dict[int, str]],
) -> str | None:
    structured_description = _structured_row_image_description(
        asset,
        primary_record=primary_record,
        header_by_sheet=header_by_sheet,
    )
    if structured_description is not None:
        return structured_description

    for text in asset.nearby_text_after:
        normalized = _string_value(text)
        if _is_usable_visual_description(normalized):
            return normalized
    for text in reversed(asset.nearby_text_before):
        normalized = _string_value(text)
        if _is_usable_visual_description(normalized):
            return normalized
    preview = _string_value(asset.raw.get("related_evidence_preview"))
    if preview is None or not _is_usable_visual_description(preview):
        return None
    return preview.splitlines()[0].strip() or None


def _structured_row_image_description(
    asset: SourceImageAsset,
    *,
    primary_record: SourceRecord,
    header_by_sheet: dict[str, dict[int, str]],
) -> str | None:
    primary_sheet_name = _optional_string(primary_record.locator.get("sheet_name"))
    primary_row_index = _row_index(primary_record)
    if primary_sheet_name is None or primary_row_index is None:
        return None
    if asset.sheet_name != primary_sheet_name or asset.row_index != primary_row_index:
        return None

    header_name = header_by_sheet.get(asset.sheet_name or "", {}).get(asset.column_index or -1)
    header_stem = _image_header_stem(header_name)
    scored_values: list[tuple[int, int, str]] = []
    for index, value in enumerate(primary_record.values):
        candidate_value = _string_value(value.value)
        if candidate_value is None or not _is_usable_visual_description(candidate_value):
            continue

        label = _optional_string(value.raw_label) or value.canonical_key
        score = _description_label_score(label, header_stem=header_stem)
        if score <= 0:
            continue
        scored_values.append((score, -index, candidate_value))

    if not scored_values:
        return None
    scored_values.sort(reverse=True)
    return scored_values[0][2]


def _image_header_stem(header_name: str | None) -> str | None:
    if header_name is None:
        return None
    stem = header_name
    for token in _IMAGE_LABEL_TOKENS:
        stem = re.sub(re.escape(token), "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s+", "", stem)
    return stem or None


def _description_label_score(label: str | None, *, header_stem: str | None) -> int:
    if label is None:
        return 0
    normalized_label = re.sub(r"\s+", "", label).casefold()
    if not normalized_label or any(token.casefold() in normalized_label for token in _IMAGE_LABEL_TOKENS):
        return 0

    has_description_token = any(token.casefold() in normalized_label for token in _DESCRIPTION_LABEL_TOKENS)
    if not has_description_token:
        return 0

    if header_stem:
        normalized_stem = header_stem.casefold()
        if normalized_label.startswith(normalized_stem):
            return 100
        if normalized_stem in normalized_label:
            return 90
    return 50


def _is_usable_visual_description(text: str | None) -> bool:
    if text is None:
        return False
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return False
    if normalized.casefold() in _GENERIC_IMAGE_TEXTS:
        return False
    if "Sheet=" in normalized and "Range=" in normalized and " | " in normalized:
        return False
    return True


def _row_index(record: SourceRecord) -> int | None:
    value = record.locator.get("row_index")
    return value if isinstance(value, int) else None


def _normalize(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    canonical = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE).strip("_")
    return canonical.casefold() or normalized.casefold()


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
