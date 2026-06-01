from __future__ import annotations

from doctransai.models.source import ProvenanceRef, SourceImageAsset, SourceModel, SourceRecord, SourceValue
from doctransai.source_model.instances import (
    build_source_instance_index,
    constraint_scoped_instance_for_provenance,
    constraint_scoped_instance_for_record,
)


def test_build_source_instance_index_groups_sheet_rows_and_assets_without_mutating_source_model() -> None:
    row_3 = SourceRecord(
        record_id="range-3",
        document_id="doc-xlsx",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 3},
        values=[SourceValue(canonical_key="项目名称", value="项目A", raw_label="项目名称")],
    )
    row_4 = SourceRecord(
        record_id="range-4",
        document_id="doc-xlsx",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 4},
        values=[SourceValue(canonical_key="项目名称", value="项目B", raw_label="项目名称")],
    )
    image = SourceImageAsset(
        asset_id="img-row-3",
        document_id="doc-xlsx",
        source_path="/input/source.xlsx",
        sheet_name="Sheet0",
        row_index=3,
        source_ref="final_images/row3.jpg",
    )
    source_model = SourceModel(records=[row_3, row_4], image_assets=[image])

    index = build_source_instance_index(source_model)

    row_3_instance = index.instance_for_record("range-3")
    row_4_instance = index.instance_for_record("range-4")

    assert row_3_instance is not None
    assert row_3_instance.instance_kind == "sheet_row"
    assert row_3_instance.container_id == "Sheet0"
    assert row_3_instance.row_index == 3
    assert row_3_instance.record_ids == ["range-3"]
    assert row_3_instance.asset_ids == ["img-row-3"]
    assert row_4_instance is not None
    assert row_4_instance.asset_ids == []
    assert index.cluster_for_instance(row_3_instance.instance_id).cluster_kind == "sheet"
    assert [record.record_id for record in source_model.records] == ["range-3", "range-4"]


def test_build_source_instance_index_groups_table_rows_under_table_cluster() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="tblrow-3",
                document_id="doc-docx",
                source_path="/input/source.docx",
                table_id="tbl-1",
                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 3},
                values=[SourceValue(canonical_key="隐患描述", value="围挡缺失")],
            ),
            SourceRecord(
                record_id="tblrow-4",
                document_id="doc-docx",
                source_path="/input/source.docx",
                table_id="tbl-1",
                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 4},
                values=[SourceValue(canonical_key="隐患描述", value="临边防护缺失")],
            ),
        ]
    )

    index = build_source_instance_index(source_model)

    row_3_instance = index.instance_for_record("tblrow-3")
    row_4_instance = index.instance_for_record("tblrow-4")

    assert row_3_instance is not None
    assert row_3_instance.instance_kind == "table_row"
    assert row_3_instance.container_id == "tbl-1"
    assert row_3_instance.row_index == 3
    assert row_4_instance is not None
    assert index.cluster_for_instance(row_3_instance.instance_id) == index.cluster_for_instance(row_4_instance.instance_id)
    assert index.cluster_for_instance(row_3_instance.instance_id).instance_ids == [
        row_3_instance.instance_id,
        row_4_instance.instance_id,
    ]


def test_build_source_instance_index_attaches_table_row_assets_to_table_cluster() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="tblrow-3",
                document_id="doc-docx",
                source_path="/input/source.docx",
                table_id="tbl-1",
                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 3},
                values=[SourceValue(canonical_key="隐患描述", value="围挡缺失")],
            ),
            SourceRecord(
                record_id="sheetrow-3",
                document_id="doc-docx",
                source_path="/input/source.docx",
                locator={"sheet_name": "Sheet0", "row_index": 3},
                values=[SourceValue(canonical_key="项目名称", value="项目A")],
            ),
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="img-table-row-3",
                document_id="doc-docx",
                source_path="/input/source.docx",
                sheet_name="Sheet0",
                row_index=3,
                source_ref="final_images/table-row3.jpg",
                raw={"table_id": "tbl-1"},
            )
        ],
    )

    index = build_source_instance_index(source_model)

    table_row_instance = index.instance_for_record("tblrow-3")
    sheet_row_instance = index.instance_for_record("sheetrow-3")
    asset_instance = index.instance_for_asset("img-table-row-3")

    assert table_row_instance is not None
    assert sheet_row_instance is not None
    assert asset_instance == table_row_instance
    assert table_row_instance.asset_ids == ["img-table-row-3"]
    assert sheet_row_instance.asset_ids == []
    assert index.cluster_for_instance(table_row_instance.instance_id).cluster_kind == "table"
    assert index.cluster_for_instance(table_row_instance.instance_id).asset_ids == ["img-table-row-3"]


def test_build_source_instance_index_keeps_unscoped_records_as_record_instances() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-pdf",
                source_path="/input/report.pdf",
                evidence_id="ev-1",
                locator={"page_anchor": "page_1"},
                values=[SourceValue(canonical_key="text", value="长文档摘要片段")],
            )
        ]
    )

    index = build_source_instance_index(source_model)
    instance = index.instance_for_record("ev-1")

    assert instance is not None
    assert instance.instance_kind == "record"
    assert instance.container_id == "doc-pdf"
    assert instance.row_index is None
    assert instance.record_ids == ["ev-1"]
    assert index.cluster_for_instance(instance.instance_id).cluster_kind == "document"


def test_constraint_scoped_instance_for_provenance_resolves_prefixed_table_record_ids() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="tblrow-3",
                document_id="doc-docx",
                source_path="/input/source.docx",
                table_id="tbl-1",
                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 3},
                values=[SourceValue(canonical_key="隐患描述", value="围挡缺失")],
            )
        ]
    )
    index = build_source_instance_index(source_model)

    instance = constraint_scoped_instance_for_provenance(
        index,
        ProvenanceRef(
            source_kind="table_cell",
            document_id="doc-docx",
            object_id="tblrow-3:0:agent_candidate",
            locator={"page_anchor": "page_1"},
            source_path="/input/source.docx",
        ),
    )

    assert instance == index.instance_for_record("tblrow-3")


def test_constraint_scoped_instance_helpers_do_not_promote_unscoped_record_instances() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-pdf",
                source_path="/input/report.pdf",
                evidence_id="ev-1",
                locator={"page_anchor": "page_1"},
                values=[SourceValue(canonical_key="text", value="长文档摘要片段")],
            )
        ]
    )
    index = build_source_instance_index(source_model)

    assert constraint_scoped_instance_for_record(index, "ev-1") is None
    assert (
        constraint_scoped_instance_for_provenance(
            index,
            ProvenanceRef(
                source_kind="evidence",
                document_id="doc-pdf",
                object_id="ev-1",
                locator={"page_anchor": "page_1"},
                source_path="/input/report.pdf",
            ),
        )
        is None
    )
