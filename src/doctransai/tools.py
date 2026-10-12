"""Model-facing schemas and dispatch; business decisions stay with the model."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from doctransai.documents.preview import image_part


def obj(properties, required=()):
    return dict(type="object", properties=properties, required=list(required), additionalProperties=False)


TEXT = {"type": "string"}
ID = {"type": "string", "minLength": 1, "maxLength": 256}
REFS = {"type": "array", "items": ID, "maxItems": 100, "uniqueItems": True}
IMAGES = {**REFS, "minItems": 1, "maxItems": 12}
ALIGN = {"enum": ["left", "center", "right", "justify"]}
HEIGHT = {"type": "number", "exclusiveMinimum": 0, "maximum": 8}
CONTENT = {"oneOf": [obj(dict(text=TEXT, alignment=ALIGN), ["text"]),
                      obj(dict(asset_ids=IMAGES, max_height_inches=HEIGHT), ["asset_ids"])]}
BASE = dict(target=ID, source_refs=REFS, reason={"type": "string", "minLength": 1})
EDITS = {"type": "array", "minItems": 1, "maxItems": 40, "items": {"oneOf": [
    obj(dict(BASE, op={"const": "replace_range"}, start={"type": "integer", "minimum": 0}, end={"type": "integer", "minimum": 1},
             expected=TEXT, text=TEXT, style_run_index={"type": "integer", "minimum": 0}), ["op", "target", "start", "end", "expected", "text", "source_refs", "reason"]),
    obj(dict(BASE, op={"const": "replace_ranges"}, replacements={"type": "array", "minItems": 1, "maxItems": 40,
        "items": obj(dict(start={"type": "integer", "minimum": 0}, end={"type": "integer", "minimum": 1}, expected=TEXT, text=TEXT,
                          style_run_index={"type": "integer", "minimum": 0}), ["start", "end", "expected", "text"])}),
        ["op", "target", "replacements", "source_refs", "reason"]),
    obj(dict(BASE, op={"const": "set_list"}, items={"type": "array", "items": TEXT, "minItems": 1, "maxItems": 100},
             style={"enum": ["decimal", "bullet"]}, start={"type": "integer", "minimum": 1, "maximum": 10000}), ["op", "target", "items", "style", "source_refs", "reason"]),
    obj(dict(BASE, op={"const": "set_text"}, text=TEXT, alignment=ALIGN), ["op", "target", "text", "source_refs", "reason"]),
    obj(dict(BASE, op={"const": "replace_text"}, old={"type": "string", "minLength": 1}, text=TEXT), ["op", "target", "old", "text", "source_refs", "reason"]),
    obj(dict(BASE, op={"const": "set_images"}, asset_ids=IMAGES, max_height_inches=HEIGHT), ["op", "target", "asset_ids", "source_refs", "reason"]),
    obj(dict(BASE, op={"const": "format_row"}, format={**obj(dict(
        height_rule={"enum": ["auto", "at_least", "exact"]}, height_pt={"type": "number", "exclusiveMinimum": 0, "maximum": 1500},
        allow_split={"type": "boolean"})), "minProperties": 1}), ["op", "target", "format", "source_refs", "reason"]),
    obj(dict(BASE, op={"const": "format_paragraph"}, format={**obj(dict(
        keep_with_next={"type": "boolean"}, keep_together={"type": "boolean"}, page_break_before={"type": "boolean"},
        space_before_pt={"type": "number", "minimum": 0, "maximum": 100},
        space_after_pt={"type": "number", "minimum": 0, "maximum": 100},
        line_spacing_pt={"type": "number", "minimum": 1, "maximum": 100},
        font_size_pt={"type": "number", "minimum": 1, "maximum": 72})), "minProperties": 1}),
        ["op", "target", "format", "source_refs", "reason"]),
    obj(dict(op={"enum": ["repeat_paragraphs", "repeat_rows"]}, keep_together={"type": "boolean"}, targets={**REFS, "minItems": 1, "maxItems": 10},
             items={"type": "array", "minItems": 1, "maxItems": 30,
                    "items": obj(dict(source_refs={**REFS, "minItems": 1}, contents={"type": "array", "items": CONTENT, "minItems": 1}), ["source_refs", "contents"])},
             reason={"type": "string", "minLength": 1}), ["op", "targets", "items", "reason"]),
]}}


def tool(name, description, schema):
    return dict(type="function", function=dict(name=name, description=description, parameters=schema))


TOOLS = [
    tool("read_source", "Read full native DataProxy objects including locator/section titles, or search them. Truncated results return next_offset; do not treat omitted text as absent evidence.",
         obj(dict(refs={**REFS, "minItems": 1, "maxItems": 4}, query={"type": "string", "minLength": 1},
                  offset={"type": "integer", "minimum": 0}, max_chars={"type": "integer", "minimum": 100, "maximum": 16000}))),
    tool("view_source_page", "View a one-based source page. Uses a native scanned_page asset when unambiguous; otherwise renders the selected source file. Local page numbers are NOT assumed to match DataProxy page anchors.",
         obj(dict(page_number={"type": "integer", "minimum": 1}), ["page_number"])),
    tool("view_source_asset", "View actual source images and their anchors/context before selecting photos. Asset IDs are native refs; do not send file paths.",
         obj(dict(refs={**REFS, "minItems": 1, "maxItems": 4}), ["refs"])),
    tool("inspect_document", "Read current version and exact node IDs, including fixed labels and blank areas. No semantic slots are preselected. Optional node_ids restricts returned content and exposes exact run offsets/styles; default is a compact full structure.",
         obj(dict(node_ids=REFS))),
    tool("edit_document", "Apply a versioned atomic batch. Operations are sequential and failures roll back the whole batch. replace_ranges edits multiple non-overlapping ranges in one paragraph; all offsets, expected text and style_run_index refer to that operation's starting snapshot, independent of range order. Response contains only changed/new nodes and removed_node_ids; unchanged prior IDs remain valid. Reusing identical batch_id is idempotent; changed arguments require a new ID. replace_range edits a paragraph by Unicode code-point [start,end) offsets plus exact expected text; optional style_run_index selects an existing run style explicitly. set_list replaces a paragraph or cell with real decimal/bullet list paragraphs, items must not include typed numbering. repeat_rows replaces consecutive row IDs with all groups: contents follow physical cells in row order, counting horizontal merged cells once and excluding vertical-merge continuations; select complete vertical-merge groups. set_text replaces whole text; replace_text preserves surrounding runs; set_images replaces an image region; multiple asset_ids share that region and do not create separate captions. Use repeat_paragraphs for independently captioned image groups. repeat_paragraphs REPLACES the prototype paragraphs with ALL complete groups, including the first. For targets=[image_node,caption_node], each item must have contents=[{asset_ids:[...]},{text:...}]; items=[first_pair,second_pair,...]. Do not fill the prototypes before repeating them. format_row controls row auto/at_least/exact height (height_pt required for non-auto) and allow_split; use row IDs. format_paragraph adjusts spacing/font/page-break/keep flags without changing text; no fact refs needed. Text deletion needs no invented source; new facts require source_refs. Optional alignment improves long text; max_height_inches fits images.",
         obj(dict(batch_id=ID, version={"type": "integer", "minimum": 0}, edits=EDITS), ["batch_id", "version", "edits"])),
    tool("preview_document", "View output (default) or original template pages. In ordinary conversion the program automatically renders the current output after a successful edit and provides those pages to the next model request; do not request the same pages again. Use this tool for template pages, missing output pages, or an on-demand check after a repair.",
         obj(dict(target={"enum": ["output", "template"]}, start_page={"type": "integer", "minimum": 1}, max_pages={"type": "integer", "minimum": 1, "maximum": 4}))),
    tool("finish", "Declare the deliverable after viewing the current output pages. Provide a short summary and only unresolved issues or missing facts. This is an editor self-check, not independent semantic validation. The legacy checks field is optional and may be a string or list.",
         obj(dict(summary=TEXT,
                  checks={"oneOf": [TEXT, {"type": "array", "items": TEXT}]},
                  issues={"type": "array", "items": TEXT},
                  missing={"type": "array", "items": obj(dict(target=TEXT, kind={"enum": ["source_missing", "manual", "ambiguous", "unsupported"]}, message=TEXT), ["target", "kind", "message"])}),
             ["summary"])),
]
XLSX_VALUE = {"oneOf": [{"type": ["string", "number", "boolean", "null"]}, obj(dict(date=TEXT), ["date"])]}
XLSX_TARGET = {"type": "string", "pattern": r"^s[0-9]+![A-Z]+[1-9][0-9]*(?::[A-Z]+[1-9][0-9]*)?$"}
XLSX_BASE = {**BASE, "target": XLSX_TARGET}
XLSX_EDITS = {"type": "array", "minItems": 1, "maxItems": 40, "items": {"oneOf": [
    obj(dict(XLSX_BASE, op={"const": "set_cells"}, values={"type": "array", "minItems": 1, "maxItems": 100,
        "items": {"type": "array", "items": XLSX_VALUE, "minItems": 1, "maxItems": 100}}, number_format=TEXT),
        ["op", "target", "values", "source_refs", "reason"]),
    obj(dict(XLSX_BASE, op={"const": "set_formula"}, formula=TEXT, expected_formula={"type": ["string", "null"]}),
        ["op", "target", "formula", "expected_formula", "source_refs", "reason"]),
    obj(dict(XLSX_BASE, op={"const": "copy_rows"}, destination_rows={"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 1, "maxItems": 100, "uniqueItems": True}),
        ["op", "target", "destination_rows", "source_refs", "reason"]),
    obj(dict(XLSX_BASE, op={"const": "set_cell_images"}, asset_ids={**REFS, "maxItems": 12}), ["op", "target", "asset_ids", "source_refs", "reason"]),
    obj(dict(XLSX_BASE, op={"const": "format_cells"}, format={**obj(dict(wrap_text={"type": "boolean"},
        horizontal={"enum": ["left", "center", "right", "general", "justify"]}, vertical={"enum": ["top", "center", "bottom"]},
        row_height={"type": "number", "minimum": 1, "maximum": 409}, column_width={"type": "number", "minimum": 1, "maximum": 255},
        font_size={"type": "number", "minimum": 6, "maximum": 72}, number_format=TEXT)), "minProperties": 1}),
        ["op", "target", "format", "source_refs", "reason"]),
    obj(dict(XLSX_BASE, op={"const": "set_print_area"}, orientation={"enum": ["portrait", "landscape"]},
        fit_to_width={"type": "integer", "minimum": 0, "maximum": 10}, repeat_rows={"type": "string", "pattern": "^[1-9][0-9]*:[1-9][0-9]*$"}, repeat_columns={"type": "string", "pattern": "^[A-Z]+:[A-Z]+$"}),
        ["op", "target", "source_refs", "reason"]),
]}}


def tools_for_format(format_key):
    if format_key != "xlsx":
        return TOOLS
    from copy import deepcopy
    result = deepcopy(TOOLS)
    inspect = next(t["function"] for t in result if t["function"]["name"] == "inspect_document")
    inspect["description"] = "Inspect sheets, formulas, merged cells, image anchors and print settings. The default view reports each sheet's used range and non-empty cells only; it does not expand every blank cell. node_ids may contain exact ranges like s0!A21:Y40 to read complete cells, blank areas and formatting. s0 indexes the first sheet regardless of its name."
    edit = next(t["function"] for t in result if t["function"]["name"] == "edit_document")
    edit["parameters"]["properties"]["edits"] = XLSX_EDITS
    edit["description"] = "Atomic versioned XLSX batch; targets use s0!A3 or s0!A3:Y5. set_cells writes an exactly shaped matrix: numbers/bools stay typed; {date: ISO} creates Excel dates; null clears; strings starting '=' remain literal. Existing formulas are protected. set_formula requires expected_formula (null for a new formula). copy_rows copies the given row/column block to empty destination start rows, translating relative formulas and preserving styles/complete merges; never inserts or shifts other rows. Copy before filling facts/images, then populate each new record separately. set_cell_images replaces images anchored at one cell; [] removes example images. Size rows/columns BEFORE images to fit them. format_cells changes explicit formatting. set_print_area sets the exact populated print range, orientation, repeat_rows such as 1:2, repeat_columns such as A:B for record identity across horizontal pages, and optional fit_to_width (0 preserves readable scale across pages). Do not squash many columns to an unreadable single page. Formatting, clearing values/images and copying templates need no invented fact refs; new facts need refs."
    return result




def _deletion_only(old: str, new: str) -> bool:
    """Removing markers/spacing is not adding a fact and needs no invented ref."""
    remaining = iter("".join(old.split()))
    return all(any(existing == character for existing in remaining) for character in "".join(new.split()))


class ToolRuntime:
    def __init__(self, source, editor, previewer):
        self.source, self.editor, self.previewer = source, editor, previewer
        self.format_key = getattr(editor, "format_key", "docx")
        self.tools = tools_for_format(self.format_key)
        self.validators = {t["function"]["name"]: Draft202012Validator(t["function"]["parameters"]) for t in self.tools}
        self.round = 0
        self.preview_round = -1
        self.preview_version = -1
        self.coverage: set[int] = set()
        self.output_pages: list[Path] = []
        self.finished = None

    def invoke(self, name: str, args: dict) -> tuple[object, list[dict]]:
        if name not in self.validators:
            raise ValueError(f"Unknown tool {name}")
        self.validators[name].validate(args)
        if name == "read_source":
            return self.source.read(**args), []
        if name == "inspect_document" and self.format_key == "xlsx":
            return self.editor.inspect(detail=bool(args.get("node_ids")), node_ids=args.get("node_ids")), []
        if name == "inspect_document":
            snapshot = self.editor.inspect(detail=bool(args.get("node_ids")))
            if args.get("node_ids"):
                wanted = set(args["node_ids"])
                unknown = wanted - set(self.editor.nodes)
                if unknown:
                    raise ValueError(f"Unknown/stale node IDs: {sorted(unknown)}")
                snapshot["nodes"] = [n for n in snapshot["nodes"] if n["id"] in wanted]
            return snapshot, []
        if name == "view_source_page":
            metadata, path = self.previewer.source_page(self.source, args["page_number"])
            return metadata, [{"type": "text", "text": json.dumps(metadata, ensure_ascii=False)}, image_part(path)]
        if name == "view_source_asset":
            parts, metadata = [], []
            for ref in args["refs"]:
                if ref not in self.source.assets:
                    raise ValueError(f"Unknown source image ID: {ref}. Use native asset IDs, not file paths. Available IDs: {list(self.source.assets)[:12]}")
                path = self.source.asset_path(ref)
                metadata.append(dict(ref=ref, context=self.source.assets[ref]))
                parts += [{"type": "text", "text": f"Source image {ref}"}, image_part(path)]
            return metadata, parts
        if name == "edit_document":
            if args["batch_id"] in self.editor.applied_batches:
                return self.editor.apply(**args), []
            if self.format_key == "xlsx":
                for edit in args["edits"]:
                    self.source.check_refs(edit["source_refs"])
                    safe = edit["op"] in ("format_cells", "set_print_area", "copy_rows") or (edit["op"] == "set_cell_images" and not edit["asset_ids"]) or (edit["op"] == "set_cells" and all(v is None or v == "" for row in edit["values"] for v in row))
                    if not safe and not edit["source_refs"]:
                        raise ValueError("Content additions require source_refs")
                self.editor.apply(**args)
                targets = list(dict.fromkeys(e["target"] for e in args["edits"]))
                result = self.editor.inspect(node_ids=targets)
                result.update(already_applied=False, snapshot="affected ranges only; other addresses remain valid; inspect copied destination rows explicitly")
                return result, []
            for edit in args["edits"]:
                if edit["op"] in ("repeat_paragraphs", "repeat_rows"):
                    for item in edit["items"]:
                        self.source.check_refs(item["source_refs"])
                else:
                    self.source.check_refs(edit["source_refs"])
                    node = self.editor.nodes.get(edit["target"])
                    if node is None:
                        raise ValueError(f"Unknown/stale target {edit['target']}")
                    deletion = edit["op"] in ("format_paragraph", "format_row") or (edit["op"] in ("set_text", "replace_text", "replace_range") and
                                _deletion_only(edit.get("expected", edit.get("old", getattr(node, "text", ""))), edit["text"]))
                    if edit["op"] == "replace_ranges":
                        deletion = all(_deletion_only(item["expected"], item["text"]) for item in edit["replacements"])
                    if not edit["source_refs"] and not deletion:
                        raise ValueError("Content additions require source_refs; deleting unsupported text does not")
            before = {n["id"]: n for n in self.editor.inspect()["nodes"]}
            result = self.editor.apply(**args)
            after = {n["id"]: n for n in result["nodes"]}
            result["nodes"] = [n for key, n in after.items() if before.get(key) != n]
            result["removed_node_ids"] = sorted(set(before) - set(after))
            result["snapshot"] = "delta: only changed/new nodes; all other prior IDs remain valid"
            return result, []
        if name == "preview_document":
            is_output = args.get("target", "output") == "output"
            pages = self.previewer.render(self.editor.output if is_output else getattr(self.editor, "reference_template", self.editor.template))
            if is_output:
                self.output_pages = pages
            start, count = args.get("start_page", 1), args.get("max_pages", 4)
            if start > len(pages):
                raise ValueError("start_page exceeds page count")
            selected = list(enumerate(pages, 1))[start - 1:start - 1 + count]
            parts = []
            for number, path in selected:
                label = f"Output version {self.editor.version}" if is_output else "Original template"
                parts += [{"type": "text", "text": f"{label}, page {number}"}, image_part(path)]
            if is_output:
                if self.preview_version != self.editor.version:
                    self.coverage.clear()
                self.preview_version, self.preview_round = self.editor.version, self.round
                self.coverage.update(number for number, _ in selected)
            next_page = start + len(selected)
            return dict(target="output" if is_output else "template", version=self.editor.version if is_output else None, page_count=len(pages),
                        delivered_pages=[number for number, _ in selected],
                        covered_output_pages=sorted(self.coverage) if is_output else None,
                        missing_output_pages=sorted(set(range(1,len(pages)+1))-self.coverage) if is_output else None,
                        next_page=next_page if next_page <= len(pages) else None), parts
        if name == "finish":
            if self.preview_version != self.editor.version or self.preview_round >= self.round:
                raise ValueError("Inspect a current output preview in an earlier model round before finishing")
            if self.coverage != set(range(1, len(self.output_pages) + 1)):
                raise ValueError(f"Not all current output pages were delivered; missing pages: {sorted(set(range(1, len(self.output_pages) + 1)) - self.coverage)}. Request them before finish.")
            # Keep completion small. ``checks`` remains accepted for old
            # callers, but is optional and is not treated as proof.
            self.finished = dict(summary=args["summary"], issues=list(args.get("issues", [])),
                                 missing=list(args.get("missing", [])))
            return {"finished": True}, []
        raise AssertionError(name)
