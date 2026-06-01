from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceInstance:
    instance_id: str
    instance_kind: str
    document_id: str | None
    source_path: str | None
    container_id: str
    row_index: int | None = None
    locator: dict[str, Any] = field(default_factory=dict)
    record_ids: list[str] = field(default_factory=list)
    asset_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SourceCluster:
    cluster_id: str
    cluster_kind: str
    document_id: str | None
    source_path: str | None
    container_id: str
    locator: dict[str, Any] = field(default_factory=dict)
    instance_ids: list[str] = field(default_factory=list)
    record_ids: list[str] = field(default_factory=list)
    asset_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SourceInstanceIndex:
    instances: list[SourceInstance] = field(default_factory=list)
    clusters: list[SourceCluster] = field(default_factory=list)
    record_to_instance_id: dict[str, str] = field(default_factory=dict)
    asset_to_instance_id: dict[str, str] = field(default_factory=dict)
    instance_to_cluster_id: dict[str, str] = field(default_factory=dict)

    @property
    def instances_by_id(self) -> dict[str, SourceInstance]:
        return {instance.instance_id: instance for instance in self.instances}

    @property
    def clusters_by_id(self) -> dict[str, SourceCluster]:
        return {cluster.cluster_id: cluster for cluster in self.clusters}

    def instance_for_record(self, record_id: str) -> SourceInstance | None:
        instance_id = self.record_to_instance_id.get(record_id)
        if instance_id is None:
            return None
        return self.instances_by_id.get(instance_id)

    def instance_for_asset(self, asset_id: str) -> SourceInstance | None:
        instance_id = self.asset_to_instance_id.get(asset_id)
        if instance_id is None:
            return None
        return self.instances_by_id.get(instance_id)

    def cluster_for_instance(self, instance_id: str) -> SourceCluster:
        cluster_id = self.instance_to_cluster_id[instance_id]
        return self.clusters_by_id[cluster_id]
