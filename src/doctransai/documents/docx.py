"""Versioned, atomic edits to a DOCX copy. No semantic mapping or LLM calls."""
from __future__ import annotations

import copy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable
import zipfile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from PIL import Image


class DocxEditor:
    def __init__(self, template: Path, output: Path, asset_path: Callable[[str], Path]):
        self.template, self.output = template.resolve(), output.resolve()
        if self.template == self.output:
            raise ValueError("Output must not overwrite the template")
        self.original_hash = hashlib.sha256(self.template.read_bytes()).hexdigest()
        self.doc = Document(self.template)
        self.asset_path = asset_path
        self.nodes, self.next_id = {}, 0
        self.version = 0
        self.applied_batches: dict[str, str] = {}
        self.touched_parts = {"word/document.xml"}
        self.inspect()
        shutil.copy2(self.template, self.output)

    @staticmethod
    def _address(node):
        element = node._element
        indexes = []
        while element.getparent() is not None:
            parent = element.getparent()
            indexes.append(parent.index(element))
            element = parent
        return str(node.part.partname), tuple(reversed(indexes))

    def inspect(self, *, _restore_ids=None) -> dict:
        known = {id(node._element): key for key, node in self.nodes.items()}
        entries = []

        def add(node, where, kind):
            key = known.get(id(node._element))
            if key is None and _restore_ids is not None:
                key = _restore_ids.get(self._address(node))
            if key is None:
                key = f"n{self.next_id}"
                self.next_id += 1
            self.nodes[key] = node
            known[id(node._element)] = key
            entries.append(dict(id=key, kind=kind, where=where, text=node.text,
                                char_count=len(node.text), nested_tables=bool(getattr(node, "tables", [])),
                                body_index=node._element.getparent().index(node._element)
                                if node._element.getparent() is self.doc._element.body else None))

        for i, p in enumerate(self.doc.paragraphs):
            add(p, f"body paragraph {i}", "paragraph")
        for ti, table in enumerate(self.doc.tables):
            seen = set()
            for ri, row in enumerate(table.rows):
                for ci, cell in enumerate(row.cells):
                    if cell._tc in seen:
                        continue
                    seen.add(cell._tc)
                    add(cell, f"table {ti} row {ri} column {ci}", "cell")
        for si, section in enumerate(self.doc.sections):
            for name in ("header", "footer", "first_page_header", "first_page_footer", "even_page_header", "even_page_footer"):
                part = getattr(section, name)
                if part.is_linked_to_previous:
                    continue
                for pi, p in enumerate(part.paragraphs):
                    add(p, f"section {si} {name} paragraph {pi}", "paragraph")
        return dict(version=self.version, nodes=entries, image_count=len(self.doc.inline_shapes),
                    supported_operations=["set_text", "replace_text", "set_images", "repeat_paragraphs", "format_paragraph"],
                    limitations=["No nested-table replacement, floating textbox editing or table-row cloning in this stage"])

    @staticmethod
    def paragraphs(node):
        if getattr(node, "tables", []):
            raise ValueError("Nested-table replacement is not supported")
        return node.paragraphs if hasattr(node, "paragraphs") else [node]

    @staticmethod
    def guard_text(p):
        if p._p.xpath(".//w:drawing | .//w:pict | .//w:fldChar | .//w:fldSimple | .//w:hyperlink | .//w:sdt"):
            raise ValueError("Text operation would damage an image, field, hyperlink or content control")

    def put_text(self, node, text, alignment=None):
        paragraphs = self.paragraphs(node)
        for p in paragraphs:
            self.guard_text(p)
        p = paragraphs[0]
        rpr = copy.deepcopy(p.runs[0]._r.rPr) if p.runs and p.runs[0]._r.rPr is not None else None
        p.clear()
        run = p.add_run(text)
        if rpr is not None:
            run._r.insert(0, rpr)
        for extra in paragraphs[1:]:
            extra._p.getparent().remove(extra._p)
        if alignment:
            p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
                           "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}[alignment]

    def replace_text(self, node, old, new):
        paragraphs = self.paragraphs(node)
        if not old or sum(p.text.count(old) for p in paragraphs) != 1:
            raise ValueError("old must occur exactly once within one paragraph; inspect the target again")
        p = next(p for p in paragraphs if old in p.text)
        self.guard_text(p)
        if "".join(r.text for r in p.runs) != p.text:
            raise ValueError("This paragraph contains unsupported non-run text")
        start, end = p.text.index(old), p.text.index(old) + len(old)
        position, matches = 0, []
        for run in p.runs:
            text = run.text
            right = position + len(text)
            if right > start and position < end:
                matches.append((run, position, right))
            position = right
        first, left, _ = matches[0]
        last, last_left, _ = matches[-1]
        prefix, suffix = first.text[:start - left], last.text[end - last_left:]
        fills = (p._p.xpath("./w:pPr/w:shd/@w:fill") or
                 p._p.xpath("ancestor::w:tc[1]/w:tcPr/w:shd/@w:fill") or
                 self.doc._element.xpath("./w:background/@w:color"))
        background = str(fills[0]).upper() if fills else "FFFFFF"
        def visible(run):
            rgb = run.font.color.rgb
            return run.font.hidden is not True and (rgb is None or str(rgb).upper() != background)
        # A match may start in an invisible X marker and continue into a visible
        # placeholder. Use the visible matched text's style, without recoloring
        # any prefix/suffix outside the replacement range.
        style_run = next((r for r, _, _ in matches if visible(r)), first)
        style = copy.deepcopy(style_run._r.rPr)
        suffix_style = copy.deepcopy(last._r.rPr)
        for run, _, _ in matches:
            run.text = ""
        first.text = prefix
        element = OxmlElement("w:r")
        first._r.addnext(element)
        inserted = Run(element, p)
        if style is not None:
            element.insert(0, style)
        inserted.text = new
        if last is first and suffix:
            element_after = OxmlElement("w:r")
            element.addnext(element_after)
            if suffix_style is not None:
                element_after.insert(0, suffix_style)
            Run(element_after, p).text = suffix
        elif last is not first:
            last.text = suffix

    def add_images(self, node, ids, max_height=2.5):
        paragraphs = self.paragraphs(node)
        p = paragraphs[0]
        # This operation explicitly replaces the image region, unlike text edits.
        p.clear()
        for extra in paragraphs[1:]:
            extra._p.getparent().remove(extra._p)
        body_width = min(s.page_width.inches - s.left_margin.inches - s.right_margin.inches for s in self.doc.sections)
        width = min(body_width, node.width.inches - .18) if getattr(node, "width", None) else body_width
        for index, ref in enumerate(ids):
            path = self.asset_path(ref)
            with Image.open(path) as image:
                w, h = image.size
            if index:
                p.add_run().add_break()
            p.add_run().add_picture(str(path), width=Inches(max(.1, min(width, max_height * w / h))))

    def apply(self, *, batch_id: str, version: int, edits: list[dict]) -> dict:
        if not batch_id or not edits:
            raise ValueError("A nonempty batch_id and edits are required")
        digest = hashlib.sha256(json.dumps(dict(version=version, edits=edits), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if batch_id in self.applied_batches:
            if self.applied_batches[batch_id] != digest:
                raise ValueError("batch_id already used for different edits")
            return dict(already_applied=True, **self.inspect())
        if version != self.version:
            raise ValueError(f"Stale document version {version}; current version is {self.version}")
        prior_ids = {self._address(node): key for key, node in self.nodes.items()}
        prior_next_id, prior_parts = self.next_id, set(self.touched_parts)
        for edit in edits:
            if edit["op"] == "repeat_paragraphs":
                expected = len(edit["targets"])
                actual = [len(item["contents"]) for item in edit["items"]]
                if any(count != expected for count in actual):
                    raise ValueError(f"Each repeated item needs {expected} contents entries in target order; got {actual}. Include the first AND subsequent complete groups; do not fill the prototypes first.")
        try:
            for edit in edits:
                op = edit["op"]
                if op == "repeat_paragraphs":
                    ids = edit["targets"]
                    if len(ids) != len(set(ids)):
                        raise ValueError("Repeated paragraph IDs must be distinct")
                    originals = [self.nodes[x] for x in ids]
                    if any(not isinstance(p, Paragraph) for p in originals):
                        raise ValueError("repeat_paragraphs requires paragraph IDs")
                    for p in originals:
                        self.guard_text(p)
                    if any(a._p.getnext() is not b._p for a, b in zip(originals, originals[1:])):
                        raise ValueError("Repeated paragraphs must be consecutive")
                    self.touched_parts.add(str(originals[0].part.partname).lstrip("/"))
                    anchor = originals[-1]._p
                    for item in edit["items"]:
                        if len(item["contents"]) != len(originals):
                            raise ValueError("Each item needs one content per original paragraph")
                        for i, (original, content) in enumerate(zip(originals, item["contents"])):
                            element = copy.deepcopy(original._p)
                            anchor.addnext(element)
                            anchor = element
                            p = Paragraph(element, original._parent)
                            if "asset_ids" in content:
                                self.add_images(p, content["asset_ids"], content.get("max_height_inches", 2.5))
                            else:
                                self.put_text(p, content["text"], content.get("alignment"))
                            p.paragraph_format.keep_together = True
                            p.paragraph_format.keep_with_next = i < len(originals) - 1
                    for ref, p in zip(ids, originals):
                        p._p.getparent().remove(p._p)
                        del self.nodes[ref]
                else:
                    node = self.nodes[edit["target"]]
                    self.touched_parts.add(str(node.part.partname).lstrip("/"))
                    if op == "set_text":
                        self.put_text(node, edit["text"], edit.get("alignment"))
                    elif op == "replace_text":
                        self.replace_text(node, edit["old"], edit["text"])
                    elif op == "set_images":
                        self.add_images(node, edit["asset_ids"], edit.get("max_height_inches", 2.5))
                    elif op == "format_paragraph":
                        for p in self.paragraphs(node):
                            options = edit["format"]
                            for key in ("keep_with_next", "keep_together", "page_break_before"):
                                if key in options:
                                    setattr(p.paragraph_format, key, options[key])
                            for key in ("space_before", "space_after", "line_spacing"):
                                if key + "_pt" in options:
                                    setattr(p.paragraph_format, key, Pt(options[key + "_pt"]))
                            if "font_size_pt" in options:
                                for run in p.runs or [p.add_run()]:
                                    run.font.size = Pt(options["font_size_pt"])
                    else:
                        raise ValueError(f"Unsupported edit operation: {op}")
            self.save()
        except Exception:
            # Deepcopy of python-docx proxies may produce a second, disconnected
            # part tree. Reload the last atomic file and bind the old IDs to it.
            self.doc = Document(self.output)
            self.nodes, self.next_id, self.touched_parts = {}, prior_next_id, prior_parts
            self.inspect(_restore_ids=prior_ids)
            raise
        self.version += 1
        self.applied_batches[batch_id] = digest
        return dict(already_applied=False, **self.inspect())

    def save(self):
        buffer = BytesIO()
        self.doc.save(buffer)
        allowed = {"[Content_Types].xml", *self.touched_parts}
        for name in self.touched_parts:
            part = Path(name)
            allowed.add(str(part.parent / "_rels" / (part.name + ".rels")))
        fd, tmp = tempfile.mkstemp(dir=self.output.parent, suffix=".docx")
        os.close(fd)
        try:
            with zipfile.ZipFile(self.template) as original, zipfile.ZipFile(buffer) as edited, zipfile.ZipFile(tmp, "w") as out:
                names = set(original.namelist())
                for info in original.infolist():
                    out.writestr(info, edited.read(info.filename) if info.filename in allowed else original.read(info.filename))
                for info in edited.infolist():
                    if info.filename not in names:
                        out.writestr(info, edited.read(info.filename))
            os.replace(tmp, self.output)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
