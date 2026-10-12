from __future__ import annotations

import re
from pathlib import Path

from doctransai.models.render_plan import RenderPlan, TextFill
from doctransai.renderers.models import RenderDiagnostic, RenderResult

_PDF_DICT_PATTERN = re.compile(r"<<(?P<body>.*?)>>", re.DOTALL)
_PDF_FIELD_NAME_PATTERN = re.compile(r"/T\s*\((?P<name>(?:\\.|[^\\)])*)\)")
_PDF_VALUE_PATTERN = re.compile(r"/V\s*(\((?:\\.|[^\\)])*\)|<[^>]*>)")


class PdfRenderer:
    format_key = "pdf"

    def render(
        self,
        plan: RenderPlan,
        *,
        bundle_dir: str | Path | None = None,
    ) -> RenderResult:
        del bundle_dir

        template_path = Path(plan.template.template_path).expanduser().resolve()
        output_path = Path(plan.output.output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload = template_path.read_bytes().decode("latin-1")
        diagnostics: list[RenderDiagnostic] = []
        applied_text_slots: list[str] = []

        for text_fill in plan.text_fills:
            payload, diagnostic = _apply_text_fill(payload, text_fill)
            if diagnostic is None:
                applied_text_slots.append(text_fill.slot_id)
            else:
                diagnostics.append(diagnostic)

        for image_placement in plan.image_placements:
            diagnostics.append(
                RenderDiagnostic(
                    severity="error",
                    code="unsupported_pdf_target",
                    message=(
                        "PDF renderer V1 only supports text fills that target a named form_field; "
                        f"slot {image_placement.slot_id} uses target_kind='{image_placement.target.target_kind}'."
                    ),
                    slot_id=image_placement.slot_id,
                    asset_id=image_placement.asset_id,
                    source_ref=image_placement.source_ref,
                )
            )

        output_path.write_bytes(payload.encode("latin-1"))
        return RenderResult(
            output_path=str(output_path),
            applied_text_slots=applied_text_slots,
            diagnostics=diagnostics,
        )


def _apply_text_fill(payload: str, text_fill: TextFill) -> tuple[str, RenderDiagnostic | None]:
    target = text_fill.target
    if target.target_kind != "form_field" or not target.form_field_name:
        return payload, RenderDiagnostic(
            severity="error",
            code="unsupported_pdf_target",
            message=(
                "PDF renderer V1 only supports text fills that target a named form_field; "
                f"slot {text_fill.slot_id} uses target_kind='{target.target_kind}'."
            ),
            slot_id=text_fill.slot_id,
        )

    matches = list(_matching_field_dictionaries(payload, target.form_field_name))
    if len(matches) != 1:
        return payload, RenderDiagnostic(
            severity="error",
            code="pdf_form_field_not_found",
            message=(
                f"PDF renderer could not find a unique AcroForm field named '{target.form_field_name}' "
                f"for slot {text_fill.slot_id}; leaving the template unchanged."
            ),
            slot_id=text_fill.slot_id,
        )

    match = matches[0]
    dictionary = match.group(0)
    encoded_value = _encode_pdf_text_string(text_fill.value)

    if _PDF_VALUE_PATTERN.search(dictionary):
        updated_dictionary = _PDF_VALUE_PATTERN.sub(f"/V {encoded_value}", dictionary, count=1)
    else:
        updated_dictionary = f"{dictionary[:-2]} /V {encoded_value}>>"

    updated_payload = f"{payload[: match.start()]}{updated_dictionary}{payload[match.end() :]}"
    return updated_payload, None


def _matching_field_dictionaries(payload: str, field_name: str):
    normalized_name = field_name.strip()
    for dictionary_match in _PDF_DICT_PATTERN.finditer(payload):
        field_name_match = _PDF_FIELD_NAME_PATTERN.search(dictionary_match.group("body"))
        if field_name_match is None:
            continue
        if _unescape_pdf_literal(field_name_match.group("name")).strip() == normalized_name:
            yield dictionary_match


def _encode_pdf_text_string(value: str) -> str:
    return f"<FEFF{value.encode('utf-16-be').hex().upper()}>"


def _unescape_pdf_literal(value: str) -> str:
    return value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
