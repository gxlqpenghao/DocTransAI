"""Readable views over DataProxy objects, without a second source model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from doctransai.data_layer.models import SourceCorpus

_IDS = {"evidence_units": "evidence_id", "section_units": "section_id",
        "block_inventory": "block_id", "table_units": "table_id", "table_rows": "table_row_id",
        "table_cells": "table_cell_id", "cell_ranges": "cell_range_id", "sheets": "sheet_id",
        "visual_asset_inventory": "asset_id"}


class SourceView:
    def __init__(self, corpus: SourceCorpus, *, document_id: str | None = None,
                 source_file: Path | None = None):
        self.corpus = corpus
        documents = {d["document_id"]: dict(d) for d in corpus.documents}
        for row in corpus.source_manifest:
            documents.setdefault(row["document_id"], {}).update(row)
        matches = list(documents.values())
        if document_id:
            matches = [d for d in matches if d["document_id"] == document_id]
        if source_file:
            source_file = source_file.expanduser().resolve()
            exact = [d for d in matches if Path(d.get("source_path", "")).resolve() == source_file]
            if not exact and source_file.is_file():
                digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
                exact = [d for d in matches if d.get("source_checksum") == digest]
            matches = exact
        if len(matches) != 1:
            raise ValueError("Select exactly one source document with --document-id or --source-file")
        self.document = matches[0]
        self.source_file = source_file or Path(self.document["source_path"]).expanduser().resolve()
        self.objects: dict[str, dict[str, Any]] = {}
        self.assets: dict[str, dict[str, Any]] = {}
        self.evidence: list[dict[str, Any]] = []
        self.kinds: dict[str, str] = {}
        self.duplicate_ids: set[str] = set()
        for component, id_key in _IDS.items():
            for row in corpus.component_records(component):
                if row.get("document_id") != self.document["document_id"]:
                    continue
                ref = row.get(id_key)
                if not isinstance(ref, str):
                    continue
                if ref in self.objects and self.objects[ref] != row:
                    previous = self.objects[ref]
                    variants = previous.get("variants", [previous]) + [row]
                    self.objects[ref] = dict(native_id=ref, variants=variants)
                    self.duplicate_ids.add(ref)
                    if component == "visual_asset_inventory":
                        # Some upstream files repeat one asset ID/file with different
                        # bbox annotations. Preserve every annotation, never last-write-wins.
                        common = {key: variants[0].get(key) for key in ("asset_type", "source_ref", "page_anchor", "checksum")
                                  if all(v.get(key) == variants[0].get(key) for v in variants)}
                        self.assets[ref] = dict(asset_id=ref, variants=variants, **common)
                    continue
                self.objects[ref] = row
                self.kinds[ref] = component
                if component == "evidence_units":
                    self.evidence.append(row)
                if component == "visual_asset_inventory":
                    self.assets[ref] = row

    def check_refs(self, refs: list[str] | tuple[str, ...]):
        missing = [ref for ref in refs if ref not in self.objects]
        if missing:
            raise ValueError(f"Unknown/out-of-document source refs: {missing}")

    def asset_path(self, ref: str) -> Path:
        if ref not in self.assets:
            raise ValueError(f"Unknown source image: {ref}")
        row = self.assets[ref]
        if not row.get("source_ref"):
            raise ValueError(f"Image has no source_ref: {ref}")
        path = Path(row["source_ref"]).expanduser()
        if path.is_absolute():
            candidates = [path]
        else:
            base = self.corpus.bundle_path.parent
            checksum = self.document.get("source_checksum")
            candidates = [base / path]
            if checksum:
                candidates += [base / "parsed" / checksum / path, base / checksum / path]
        existing = list(dict.fromkeys(p.resolve() for p in candidates if p.is_file()))
        if len(existing) != 1:
            raise ValueError(f"Image path missing or ambiguous for {ref}: {len(existing)} files")
        checksum = row.get("checksum")
        if checksum and len(checksum) == 64 and hashlib.sha256(existing[0].read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Image checksum differs from DataProxy inventory: {ref}")
        return existing[0]

    def read(self, *, refs: list[str] | None = None, query: str | None = None,
             offset: int = 0, max_chars: int = 12000) -> dict[str, Any]:
        if bool(refs) == bool(query):
            raise ValueError("Provide refs OR query")
        if query:
            hits = []
            for ref, row in self.objects.items():
                text = json.dumps(row, ensure_ascii=False)
                at = text.casefold().find(query.casefold())
                if at >= 0:
                    hits.append(dict(ref=ref, snippet=text[max(0, at - 120):at + 400]))
            return dict(matches=hits[:20], total_matches=len(hits), truncated=len(hits) > 20)
        self.check_refs(refs or [])
        objects = []
        for ref in refs or []:
            text = json.dumps(self.objects[ref], ensure_ascii=False)
            objects.append(dict(ref=ref, json_text=text[offset:offset + max_chars], total_chars=len(text),
                                next_offset=offset + max_chars if offset + max_chars < len(text) else None))
        return dict(objects=objects)

    def initial(self, max_chars: int) -> dict[str, Any]:
        evidence, used = [], 0
        for row in self.evidence:
            view = {key: row.get(key) for key in ("evidence_id", "text", "locator", "object_id", "asset_refs")}
            size = len(json.dumps(view, ensure_ascii=False))
            if used + size <= max_chars:
                evidence.append(view)
                used += size
        return dict(document=self.document, evidence=evidence, evidence_total=len(self.evidence),
                    evidence_omitted=len(self.evidence) - len(evidence),
                    repeated_native_ids=sorted(self.duplicate_ids),
                    catalog=[dict(ref=ref, kind=self.kinds[ref],
                                  title=row.get("section_title") or row.get("table_title") or row.get("block_type"),
                                  preview=str(row.get("source_text") or row.get("range_text") or "")[:160])
                             for ref, row in self.objects.items() if self.kinds[ref] not in ("table_cells", "table_rows")],
                    images=[dict(ref=ref, asset_type=row.get("asset_type"), page_anchor=row.get("page_anchor"),
                                 cell_anchor=row.get("cell_anchor"), caption=row.get("caption"),
                                 nearby_text_before=str(row.get("nearby_text_before") or "")[:300],
                                 nearby_text_after=str(row.get("nearby_text_after") or "")[:300])
                            for ref, row in self.assets.items()],
                    note="Full native objects including locator/section titles are available with read_source; image context snippets may be truncated.")
