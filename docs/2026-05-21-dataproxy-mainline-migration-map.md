# DataProxy Mainline Migration Map

> **For agentic workers:** This document is for the later standalone-delivery phase. Current V1 may import/call DataProxy as upstream, but must not modify DataProxy source code. When standalone migration begins, port DocTransAI ingestion from DataProxy's actual fresh asset-pack mainline, not from isolated parser names or convenient modules.

**Goal:** Define the exact DataProxy runtime chain that DocTransAI must migrate or rewrite before template mapping/rendering begins.

**Architecture:** DocTransAI should reproduce DataProxy's no-database fresh asset-pack pipeline through `ParsedDocumentBundle v0`, then stop before DB/export/search/API layers.

**Tech Stack:** Python 3.12, MinerU adapter for `doc/docx/pdf`, native Excel parser for `xlsx`, JSONL sidecars, JSON Schema validation.

---

## 1. Migration Boundary

DocTransAI migrates the DataProxy chain from raw source files through bundle writing:

```text
source files
 -> scan_file
 -> parser routing
 -> parser.parse
 -> MinerU paired/structure validation for mineru parser
 -> quality gate and remediation
 -> reload repaired artifact when remediation writes one
 -> normalize_artifact
 -> build_data_asset_pack_rows_from_bundle
 -> build_visual_asset_inventory
 -> link_evidence_visual_assets
 -> build_block_inventory
 -> build_sheet_inventory / build_cell_range_inventory
 -> qa_seed pipeline
 -> data_quality_report / visual_quality_report
 -> fresh_validation_report
 -> diagnostics
 -> parsed_document_bundle.json + sidecar JSONL
```

DocTransAI stops here. It does **not** migrate:

- DataProxy DB exporter.
- ORM/database write path.
- Alembic migrations.
- retrieval/vector/search/index.
- API service.
- agent runtime.

## 2. Actual DataProxy Mainline

The main entry is:

```text
/Users/paul/Coding/DataProxy/src/dataproxy/data_assets/fresh_validation.py
  run_fresh_asset_pack_validation(...)
```

Within each source file, the exact order is:

1. `scan_file(source_path)`
2. `_parser_for_path(...)`
3. `artifact = parser.parse(source_path)`
4. If `parser.name == "mineru"`: `enrich_artifact_with_paired_validation(...)`
5. `_asset_base_dir_for_initial_artifact(...)`
6. `_run_quality_gate(...)`
7. If remediation writes an artifact:
   - `load_repaired_xlsx_artifact(...)` for `excel_native`
   - `load_repaired_mineru_artifact(...)` otherwise
8. `normalize_artifact(artifact)`
9. `build_data_asset_pack_rows_from_bundle(...)`
10. `build_visual_asset_inventory(...)`
11. `link_evidence_visual_assets(...)`
12. `build_block_inventory(...)`
13. `build_sheet_inventory(...)`
14. `build_cell_range_inventory(...)`
15. append document summary

After all files:

1. `_write_data_asset_rows(...)`
2. `write_visual_asset_inventory(...)`
3. write block/sheet/cell sidecars
4. `_build_qa_seed_outputs(...)`
5. `build_data_quality_report(...)`
6. `write_data_quality_report(...)`
7. `build_visual_quality_report(...)`
8. `write_visual_quality_report(...)`
9. `_build_fresh_validation_report(...)`
10. `build_diagnostics(...)`
11. `write_diagnostics(...)`
12. `_build_parsed_document_bundle_manifest(...)`
13. write `parsed_document_bundle.json`
14. write `fresh_validation_report.json`

## 3. Parser Routing

DataProxy route source of truth:

```text
/Users/paul/Coding/DataProxy/src/dataproxy/ingestion/router.py
```

For DocTransAI V1:

| Extension | DataProxy mainline parser | DocTransAI parser key |
| --- | --- | --- |
| `.doc` | `MinerUParser` | `mineru_document` |
| `.docx` | `MinerUParser` | `mineru_document` |
| `.pdf` | `MinerUParser` | `mineru_document` |
| `.xlsx` | `ExcelParser` through fresh-validation override | `xlsx_native` |

Important correction:

- `docx_native_parser.py` exists in DataProxy, but it is not the source-document mainline for `docx` in the fresh asset-pack route.
- In DocTransAI, native docx/OOXML code belongs to template analysis, rendering, or remediation helpers, not the source-ingestion main parser.

## 4. File Migration Map

### Orchestration

| DataProxy | DocTransAI target | Notes |
| --- | --- | --- |
| `data_assets/fresh_validation.py` | `ingestion/pipeline.py` and `ingestion/asset_pack/*` | Port the orchestration shape first. |
| `scripts/validate_fresh_asset_pack.py` | `cli.py` subcommand later | CLI wrapper, not core logic. |

### Parser routing and artifacts

| DataProxy | DocTransAI target | Notes |
| --- | --- | --- |
| `ingestion/router.py` | `formats/registry.py` + `ingestion/pipeline.py` | Route `doc/docx/pdf` to MinerU and `xlsx` to native Excel. |
| `ingestion/models.py` | `ingestion/models.py` | Port `ParsedArtifact` and `ParsedBlock`. |
| `ingestion/scanner.py` | `ingestion/scanner.py` | File checksum/source metadata. |
| `ingestion/parsers/mineru_parser.py` | `ingestion/parsers/mineru_document.py` | Main parser for `doc/docx/pdf`. |
| `ingestion/parsers/excel_parser.py` | `ingestion/parsers/xlsx_native.py` | Main parser for `xlsx`. |

### Canonical normalization

| DataProxy | DocTransAI target |
| --- | --- |
| `canonical/models.py` | `canonical/models.py` |
| `canonical/document_normalizer.py` | `canonical/document.py` or `canonical/normalizer.py` |
| `canonical/section_normalizer.py` | `canonical/section.py` |
| `canonical/table_normalizer.py` | `canonical/table.py` |
| `canonical/sheet_normalizer.py` | `canonical/sheet.py` |
| `canonical/evidence_normalizer.py` | `canonical/evidence.py` |
| `canonical/parser_signals.py` | `canonical/parser_signals.py` |
| `canonical/source_paths.py` | `canonical/source_paths.py` |
| `canonical/subdocument_segmentation.py` | `canonical/subdocument_segmentation.py` |

### Quality gate and remediation

| DataProxy | DocTransAI target |
| --- | --- |
| `ingestion/quality_gate.py` | `ingestion/quality/gate.py` |
| `ingestion/quality_gate_runner.py` | `ingestion/quality/runner.py` |
| `ingestion/quality_remediation.py` | `ingestion/quality/remediation.py` |
| `ingestion/xlsx_quality_remediation.py` | `ingestion/quality/xlsx_remediation.py` |
| `ingestion/docx_native_image_extract.py` | `ingestion/quality/docx_image_extract.py` |
| `ingestion/xlsx_native_image_extract.py` | `ingestion/quality/xlsx_image_extract.py` |
| `ingestion/repair_writers.py` | `ingestion/quality/repair_writers.py` |
| `ingestion/structure_validation.py` | `ingestion/quality/structure_validation.py` |

### Asset pack generation

| DataProxy | DocTransAI target |
| --- | --- |
| `data_assets/block_inventory.py` | `ingestion/asset_pack/block_inventory.py` |
| `data_assets/visual_inventory.py` | `ingestion/asset_pack/visual_inventory.py` |
| `data_assets/visual_export.py` | `ingestion/asset_pack/visual_export.py` |
| `data_assets/relationships.py` | `ingestion/asset_pack/relationships.py` |
| `data_assets/spreadsheet_inventory.py` | `ingestion/asset_pack/spreadsheet_inventory.py` |
| `data_assets/table_delivery.py` | `ingestion/asset_pack/table_delivery.py` |
| `data_assets/quality.py` | `ingestion/asset_pack/quality.py` |
| `data_assets/diagnostics.py` | `ingestion/asset_pack/diagnostics.py` |
| `data_assets/qa_seed/*` | `ingestion/asset_pack/qa_seed/*` |

## 5. Implementation Rule

Each migrated slice must satisfy both conditions:

1. It follows the same stage position as DataProxy's `run_fresh_asset_pack_validation`.
2. It can produce bundle sidecars that `doctransai.data_layer.read_parsed_document_bundle()` can read and validate.

This means the next implementation step is not “pick a parser file and port it”. The next step is:

```text
Port the fresh-validation orchestration skeleton into `src/doctransai/ingestion/pipeline.py`,
with parser hooks for `mineru_document` and `xlsx_native`.
```

After that, fill parser implementations in the same order the orchestration calls them.
