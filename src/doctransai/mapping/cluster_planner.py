from __future__ import annotations

from dataclasses import dataclass, field

from doctransai.models.source import SourceModel
from doctransai.models.template import TemplateModel
from doctransai.source_model.instances import build_source_instance_index


@dataclass(slots=True)
class SourceInstancePlan:
    instance_id: str
    instance_kind: str
    record_ids: list[str] = field(default_factory=list)
    asset_ids: list[str] = field(default_factory=list)
    row_index: int | None = None


@dataclass(slots=True)
class SourceClusterPlan:
    cluster_id: str
    cluster_kind: str
    instance_ids: list[str] = field(default_factory=list)
    record_count: int = 0
    asset_count: int = 0
    instances: list[SourceInstancePlan] = field(default_factory=list)


@dataclass(slots=True)
class RepeatRegionClusterPlan:
    region_id: str
    region_kind: str
    slot_ids: list[str] = field(default_factory=list)
    candidate_cluster_ids: list[str] = field(default_factory=list)
    instance_count_by_cluster_id: dict[str, int] = field(default_factory=dict)
    coverage_by_cluster_id: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass(slots=True)
class SourceClusterPlanningResult:
    clusters: list[SourceClusterPlan] = field(default_factory=list)
    repeat_region_plans: list[RepeatRegionClusterPlan] = field(default_factory=list)


def build_source_cluster_plan(
    *,
    source_model: SourceModel,
    template_model: TemplateModel,
) -> SourceClusterPlanningResult:
    index = build_source_instance_index(source_model)
    clusters = sorted(
        [_source_cluster_plan(cluster, index.instances_by_id) for cluster in index.clusters],
        key=lambda cluster: (cluster.cluster_kind, cluster.cluster_id),
    )
    cluster_by_id = {cluster.cluster_id: cluster for cluster in clusters}

    return SourceClusterPlanningResult(
        clusters=clusters,
        repeat_region_plans=[
            _repeat_region_plan(region_id=region.region_id, region_kind=region.region_kind, slot_ids=slot_ids, cluster_by_id=cluster_by_id)
            for region in template_model.repeat_regions
            if (slot_ids := _slot_ids_for_region(template_model, region.region_id))
        ],
    )


def _repeat_region_plan(
    *,
    region_id: str,
    region_kind: str,
    slot_ids: list[str],
    cluster_by_id: dict[str, SourceClusterPlan],
) -> RepeatRegionClusterPlan:
    candidate_clusters = sorted(
        [cluster for cluster in cluster_by_id.values() if len(cluster.instances) > 1],
        key=lambda cluster: (-len(cluster.instances), cluster.cluster_id),
    )
    return RepeatRegionClusterPlan(
        region_id=region_id,
        region_kind=region_kind,
        slot_ids=slot_ids,
        candidate_cluster_ids=[cluster.cluster_id for cluster in candidate_clusters],
        instance_count_by_cluster_id={
            cluster.cluster_id: len(cluster.instances)
            for cluster in candidate_clusters
        },
        coverage_by_cluster_id={
            cluster.cluster_id: {
                "instance_count": len(cluster.instances),
                "record_count": cluster.record_count,
                "asset_count": cluster.asset_count,
            }
            for cluster in candidate_clusters
        },
    )


def _slot_ids_for_region(template_model: TemplateModel, region_id: str) -> list[str]:
    return [slot.slot_id for slot in template_model.slots if slot.repeat_region_id == region_id]


def _source_cluster_plan(cluster, instances_by_id) -> SourceClusterPlan:
    instances = sorted(
        [
            SourceInstancePlan(
                instance_id=instance.instance_id,
                instance_kind=instance.instance_kind,
                record_ids=list(instance.record_ids),
                asset_ids=list(instance.asset_ids),
                row_index=instance.row_index,
            )
            for instance_id in cluster.instance_ids
            if (instance := instances_by_id.get(instance_id)) is not None
        ],
        key=_instance_sort_key,
    )
    return SourceClusterPlan(
        cluster_id=cluster.cluster_id,
        cluster_kind=cluster.cluster_kind,
        instance_ids=[instance.instance_id for instance in instances],
        record_count=len(cluster.record_ids),
        asset_count=len(cluster.asset_ids),
        instances=instances,
    )


def _instance_sort_key(instance: SourceInstancePlan) -> tuple[int, int, str]:
    if instance.row_index is None:
        return (1, 0, instance.instance_id)
    return (0, instance.row_index, instance.instance_id)
