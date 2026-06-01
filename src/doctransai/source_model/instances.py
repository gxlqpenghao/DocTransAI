from __future__ import annotations

from typing import Any

from doctransai.models.source import ProvenanceRef, SourceImageAsset, SourceModel, SourceRecord
from doctransai.models.source_instance import SourceCluster, SourceInstance, SourceInstanceIndex


CONSTRAINT_SCOPED_INSTANCE_KINDS = frozenset({"sheet_row", "table_row"})


def build_source_instance_index(source_model: SourceModel) -> SourceInstanceIndex:
    instances_by_id: dict[str, SourceInstance] = {}
    clusters_by_id: dict[str, SourceCluster] = {}
    record_to_instance_id: dict[str, str] = {}
    asset_to_instance_id: dict[str, str] = {}
    instance_to_cluster_id: dict[str, str] = {}

    for record in source_model.records:
        instance = _instance_from_record(record)
        existing = instances_by_id.get(instance.instance_id)
        if existing is None:
            instances_by_id[instance.instance_id] = instance
            existing = instance
        existing.record_ids.append(record.record_id)
        record_to_instance_id[record.record_id] = existing.instance_id

        cluster = _cluster_for_instance(existing)
        existing_cluster = clusters_by_id.get(cluster.cluster_id)
        if existing_cluster is None:
            clusters_by_id[cluster.cluster_id] = cluster
            existing_cluster = cluster
        if existing.instance_id not in existing_cluster.instance_ids:
            existing_cluster.instance_ids.append(existing.instance_id)
        existing_cluster.record_ids.append(record.record_id)
        instance_to_cluster_id[existing.instance_id] = existing_cluster.cluster_id

    for asset in source_model.image_assets:
        instance_id = _instance_id_from_asset(asset)
        if instance_id is None or instance_id not in instances_by_id:
            continue
        instance = instances_by_id[instance_id]
        instance.asset_ids.append(asset.asset_id)
        asset_to_instance_id[asset.asset_id] = instance.instance_id
        cluster_id = instance_to_cluster_id.get(instance.instance_id)
        if cluster_id is not None:
            clusters_by_id[cluster_id].asset_ids.append(asset.asset_id)

    return SourceInstanceIndex(
        instances=list(instances_by_id.values()),
        clusters=list(clusters_by_id.values()),
        record_to_instance_id=record_to_instance_id,
        asset_to_instance_id=asset_to_instance_id,
        instance_to_cluster_id=instance_to_cluster_id,
    )


def constraint_scoped_instance_for_record(
    index: SourceInstanceIndex,
    record_id: str,
) -> SourceInstance | None:
    return _constraint_scoped_instance(index.instance_for_record(record_id))


def constraint_scoped_instance_for_asset(
    index: SourceInstanceIndex,
    asset_id: str,
) -> SourceInstance | None:
    return _constraint_scoped_instance(index.instance_for_asset(asset_id))


def constraint_scoped_instance_for_provenance(
    index: SourceInstanceIndex,
    ref: ProvenanceRef,
) -> SourceInstance | None:
    if ref.asset_id:
        instance = constraint_scoped_instance_for_asset(index, ref.asset_id)
        if instance is not None:
            return instance

    for record_id in _candidate_record_ids(ref):
        instance = constraint_scoped_instance_for_record(index, record_id)
        if instance is not None:
            return instance

    return None


def _instance_from_record(record: SourceRecord) -> SourceInstance:
    row_index = _int_value(record.locator.get("row_index"))
    table_id = _string_value(record.table_id) or _string_value(record.locator.get("table_id"))
    if table_id is not None and row_index is not None:
        locator = _filtered_locator(record.locator, keys={"page_anchor", "table_id", "row_index"})
        locator["table_id"] = table_id
        return SourceInstance(
            instance_id=_row_instance_id("table_row", record.document_id, record.source_path, table_id, row_index),
            instance_kind="table_row",
            document_id=record.document_id,
            source_path=record.source_path,
            container_id=table_id,
            row_index=row_index,
            locator=locator,
        )

    sheet_name = _string_value(record.locator.get("sheet_name"))
    if sheet_name is not None and row_index is not None:
        locator = _filtered_locator(record.locator, keys={"sheet_id", "sheet_name", "row_index", "cell_range"})
        locator["sheet_name"] = sheet_name
        return SourceInstance(
            instance_id=_row_instance_id("sheet_row", record.document_id, record.source_path, sheet_name, row_index),
            instance_kind="sheet_row",
            document_id=record.document_id,
            source_path=record.source_path,
            container_id=sheet_name,
            row_index=row_index,
            locator=locator,
        )

    container_id = record.document_id or record.source_path or "unknown_document"
    return SourceInstance(
        instance_id=f"record:{record.record_id}",
        instance_kind="record",
        document_id=record.document_id,
        source_path=record.source_path,
        container_id=container_id,
        locator=dict(record.locator),
    )


def _cluster_for_instance(instance: SourceInstance) -> SourceCluster:
    if instance.instance_kind == "table_row":
        cluster_kind = "table"
        cluster_id = f"table:{_scope_key(instance.document_id, instance.source_path)}:{instance.container_id}"
    elif instance.instance_kind == "sheet_row":
        cluster_kind = "sheet"
        cluster_id = f"sheet:{_scope_key(instance.document_id, instance.source_path)}:{instance.container_id}"
    else:
        cluster_kind = "document"
        cluster_id = f"document:{_scope_key(instance.document_id, instance.source_path)}"

    return SourceCluster(
        cluster_id=cluster_id,
        cluster_kind=cluster_kind,
        document_id=instance.document_id,
        source_path=instance.source_path,
        container_id=instance.container_id,
        locator=_cluster_locator(instance),
    )


def _instance_id_from_asset(asset: SourceImageAsset) -> str | None:
    row_index = _int_value(asset.row_index)
    table_id = _string_value(asset.raw.get("table_id"))
    if table_id is not None and row_index is not None:
        return _row_instance_id("table_row", asset.document_id, asset.source_path, table_id, row_index)
    if asset.sheet_name is not None and row_index is not None:
        return _row_instance_id("sheet_row", asset.document_id, asset.source_path, asset.sheet_name, row_index)
    return None


def _row_instance_id(
    instance_kind: str,
    document_id: str | None,
    source_path: str | None,
    container_id: str,
    row_index: int,
) -> str:
    return f"{instance_kind}:{_scope_key(document_id, source_path)}:{container_id}:{row_index}"


def _scope_key(document_id: str | None, source_path: str | None) -> str:
    return document_id or source_path or "unknown"


def _cluster_locator(instance: SourceInstance) -> dict[str, Any]:
    locator = dict(instance.locator)
    locator.pop("row_index", None)
    return locator


def _filtered_locator(locator: dict[str, Any], *, keys: set[str]) -> dict[str, Any]:
    return {key: value for key, value in locator.items() if key in keys and value is not None}


def _int_value(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _constraint_scoped_instance(instance: SourceInstance | None) -> SourceInstance | None:
    if instance is None:
        return None
    if instance.instance_kind not in CONSTRAINT_SCOPED_INSTANCE_KINDS:
        return None
    return instance


def _candidate_record_ids(ref: ProvenanceRef) -> list[str]:
    record_ids: list[str] = []
    for value in (ref.object_id, ref.evidence_id):
        if not value:
            continue
        record_ids.append(value)
        prefix = value.split(":", 1)[0]
        if prefix != value:
            record_ids.append(prefix)
    return record_ids
