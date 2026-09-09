"""Readable views over DataProxy objects, without a second source model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
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
        if corpus.resource_root is not None:
            from .artifact import package_path
            packaged_source = package_path(corpus.resource_root, self.document["source_path"])
            self.source_file = source_file or packaged_source
        else:
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
        if self.corpus.resource_root is not None:
            from .artifact import package_path
            path = package_path(self.corpus.resource_root, row["source_ref"])
        else:
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

    def navigation(self, ref: str) -> dict:
        """Expose explicit native anchors only; never infer pages from text/order."""
        self.check_refs([ref])
        anchors, assets = set(), set()
        def visit(value):
            if isinstance(value, dict):
                anchor = value.get("page_anchor")
                if isinstance(anchor, str):
                    anchors.add(anchor)
                for asset in value.get("visual_asset_refs", value.get("asset_refs", [])) or []:
                    if isinstance(asset, str) and asset in self.assets:
                        assets.add(asset)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(self.objects[ref])
        for asset in assets:
            visit(self.assets[asset])
        pages = [asset for asset, row in self.assets.items()
                 if row.get("asset_type") == "scanned_page" and row.get("page_anchor") in anchors]
        return dict(native_page_anchors=sorted(anchors), asset_refs=sorted(assets),
                    scanned_page_asset_refs=pages,
                    note="Native anchors only; local office-render page correspondence is unverified. Use asset IDs for exact native pages.")

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
            return dict(matches=hits[offset:offset + 20], total_matches=len(hits),
                        next_offset=offset + 20 if offset + 20 < len(hits) else None,
                        truncated=offset + 20 < len(hits))
        self.check_refs(refs or [])
        objects = []
        for ref in refs or []:
            text = json.dumps(self.objects[ref], ensure_ascii=False)
            objects.append(dict(ref=ref, navigation=self.navigation(ref), json_text=text[offset:offset + max_chars], total_chars=len(text),
                                next_offset=offset + max_chars if offset + max_chars < len(text) else None))
        return dict(objects=objects)

    @staticmethod
    def _range_rows(value: object) -> set[int]:
        rows: set[int] = set()
        for match in re.finditer(r"\b[A-Z]{1,3}(\d+)(?::[A-Z]{1,3}(\d+))?\b", str(value or "")):
            first, last = int(match.group(1)), int(match.group(2) or match.group(1))
            rows.update(range(min(first, last), max(first, last) + 1))
        return rows

    def initial_asset_refs(self, primary_refs: list[str] | tuple[str, ...] = (), *, max_assets: int = 12) -> list[str]:
        """Select native source images for the first context using explicit anchors.

        This is an input-preparation index, not a semantic image mapper. Direct
        native refs win; spreadsheet ranges can additionally select images whose
        native cell anchor is in the same row. Remaining images stay available
        through ``view_source_asset``.
        """
        self.check_refs(primary_refs)
        selected: list[str] = []
        primary_rows: set[int] = set()
        primary_sheets: set[str] = set()

        def visit(value):
            nonlocal primary_rows
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in ("cell_range", "range", "range_text", "cell_anchor"):
                        primary_rows.update(self._range_rows(child))
                    if key in ("sheet_name", "worksheet_name") and isinstance(child, str):
                        primary_sheets.add(child)
                    if key in ("visual_asset_refs", "asset_refs") and isinstance(child, list):
                        for ref in child:
                            if ref in self.assets and ref not in selected:
                                selected.append(ref)
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        for ref in primary_refs:
            visit(self.objects[ref])

        if primary_rows:
            for ref, row in self.assets.items():
                anchor = row.get("cell_anchor")
                if (anchor and self._range_rows(anchor) & primary_rows and
                        (not primary_sheets or row.get("sheet_name") in primary_sheets) and ref not in selected):
                    selected.append(ref)

        if not primary_refs and len(self.assets) <= max_assets:
            selected.extend(ref for ref in self.assets if ref not in selected)
        elif not primary_refs and len(selected) < max_assets:
            # A short source with no explicit asset refs should still expose
            # its complete native image set; large sets remain on-demand.
            for ref in self.assets:
                if ref not in selected:
                    selected.append(ref)
                if len(selected) >= max_assets:
                    break
        return selected[:max_assets]

    def initial(self, max_chars: int, *, primary_refs: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
        """Build the first model context without creating a second source model.

        Declared primary objects get the first native slices.  The complete
        objects, including non-primary material, remain available through
        ``read_source`` and the compact catalog below.
        """
        self.check_refs(primary_refs)
        primary = list(dict.fromkeys(primary_refs))
        primary_set = set(primary)

        def related(row):
            refs = {row.get("evidence_id"), row.get("object_id"), *(row.get("visual_asset_refs", row.get("asset_refs")) or [])}
            return bool(refs & primary_set)

        primary_objects, used = [], 0
        for ref in primary:
            text = json.dumps(self.objects[ref], ensure_ascii=False)
            remaining = max(0, max_chars - used)
            if not remaining:
                break
            limit = min(len(text), remaining)
            primary_objects.append(dict(ref=ref, kind=self.kinds.get(ref), navigation=self.navigation(ref),
                                        json_text=text[:limit], total_chars=len(text),
                                        next_offset=limit if limit < len(text) else None))
            used += limit

        ordered_evidence = sorted(enumerate(self.evidence), key=lambda pair: (not related(pair[1]), pair[0]))
        evidence = []
        for _, row in ordered_evidence:
            view = {key: row.get(key) for key in ("evidence_id", "text", "locator", "object_id", "asset_refs", "visual_asset_refs")}
            size = len(json.dumps(view, ensure_ascii=False))
            if used + size <= max_chars:
                evidence.append(view)
                used += size

        catalog_rows = list(self.objects.items())
        catalog_rows.sort(key=lambda pair: (pair[0] not in primary_set, self.kinds.get(pair[0], ""), pair[0]))
        return dict(document=self.document, primary_objects=primary_objects,
                    evidence=evidence, evidence_total=len(self.evidence),
                    evidence_omitted=len(self.evidence) - len(evidence),
                    repeated_native_ids=sorted(self.duplicate_ids),
                    catalog=[dict(ref=ref, kind=self.kinds[ref],
                                  title=row.get("section_title") or row.get("table_title") or row.get("block_type"),
                                  preview=str(row.get("source_text") or row.get("range_text") or "")[:160])
                             for ref, row in catalog_rows if self.kinds[ref] not in ("table_cells", "table_rows")],
                    images=[dict(ref=ref, asset_type=row.get("asset_type"), page_anchor=row.get("page_anchor"),
                                 cell_anchor=row.get("cell_anchor"), caption=row.get("caption"),
                                 nearby_text_before=str(row.get("nearby_text_before") or "")[:300],
                                 nearby_text_after=str(row.get("nearby_text_after") or "")[:300])
                            for ref, row in self.assets.items()],
                    note="Full native objects including locator/section titles are available with read_source; image context snippets may be truncated.")
