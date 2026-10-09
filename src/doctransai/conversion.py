"""Public single-document entrypoint for the new tool path."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import time
import tempfile
import zipfile

from doctransai.agent import append_event, run_agent
from doctransai import __version__
from doctransai.config import RuntimeConfig
from doctransai.data_layer import read_parsed_document_bundle
from doctransai.data_layer.artifact import read_source_input
from doctransai.data_layer.view import SourceView
from doctransai.documents.docx import DocxEditor
from doctransai.documents.xlsx import XlsxEditor
from doctransai.documents.preview import Previewer, image_part
from doctransai.llm.client import DoctransaiLLMClient, DoctransaiLLMConfig
from doctransai.tools import tools_for_format, ToolRuntime
from doctransai.review import review_and_repair, REVIEW_TOOL
from doctransai.types import ConversionResult, TaskSpec


def convert(task: TaskSpec, *, config: RuntimeConfig | None = None, client=None, previewer=None,
            progress=None, existing_document: Path | None = None) -> ConversionResult:
    config = config or RuntimeConfig.from_environment()
    output_dir = task.output_dir.expanduser().resolve()
    if output_dir.exists():
        raise ValueError("Use a new output directory; existing runs are not overwritten")
    output_dir.mkdir(parents=True)
    started = time.monotonic()
    deadline = started + config.max_seconds
    report_path = output_dir / "review.json"
    trace_path = output_dir / "trace.jsonl"
    result = ConversionResult("failed", "not_run", None, str(report_path))
    report = dict(product_version=__version__, workflow="document-tools-v1",
                  task=asdict(task), model=config.model, reasoning_effort=config.reasoning_effort,
                  independent_semantic_review="not_run")
    editor = None
    final = None
    runtime = None
    try:
        if not task.instruction.strip():
            raise ValueError("A conversion instruction is required")
        suffix = task.template_path.suffix.lower()
        if suffix not in (".docx", ".xlsx"):
            raise ValueError("Targets must be DOCX or XLSX; legacy templates need explicit materialization first")
        if existing_document is not None and (not config.review_enabled or existing_document.suffix.lower() != suffix):
            raise ValueError("Review requires matching document/template formats and enabled review")
        reference_hash = hashlib.sha256(task.template_path.read_bytes()).hexdigest()
        tools = tools_for_format(suffix[1:])
        prompt = (Path(__file__).parent / "prompts/document_editing_policy.md").read_text()
        (output_dir / "task.json").write_text(json.dumps(dict(task=asdict(task), config=asdict(config),
            existing_document=str(existing_document) if existing_document else None,
            existing_document_sha256=hashlib.sha256(existing_document.read_bytes()).hexdigest() if existing_document else None,
            review_prompt_sha256=hashlib.sha256((Path(__file__).parent / "prompts/document_review_policy.md").read_bytes()).hexdigest(),
            review_tool_sha256=hashlib.sha256(json.dumps(REVIEW_TOOL,sort_keys=True).encode()).hexdigest(),
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            tools_sha256=hashlib.sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest()), default=str, ensure_ascii=False, indent=2))
        if progress:
            progress("读取DataProxy原生材料")
        corpus = (read_source_input(task.bundle_path, output_dir)
                  if task.bundle_path.is_dir() or task.bundle_path.name == "manifest.json" or task.bundle_path.suffix.lower() == ".zip"
                  else read_parsed_document_bundle(task.bundle_path))
        if corpus.artifact_manifest:
            report["parse_artifact"] = {k: corpus.artifact_manifest[k] for k in ("contract_version", "job_id", "quality")}
        source = SourceView(corpus, document_id=task.document_id, source_file=task.source_file)
        source.check_refs(task.source_refs)
        editor = (XlsxEditor if suffix == ".xlsx" else DocxEditor)(existing_document or task.template_path, output_dir / ("working" + suffix), source.asset_path)
        editor.reference_template = task.template_path.resolve()
        reference_editor_for_snapshot = editor
        if existing_document is not None:
            with tempfile.TemporaryDirectory() as tmp:
                reference_editor = (XlsxEditor if suffix == ".xlsx" else DocxEditor)(task.template_path, Path(tmp) / ("reference" + suffix), source.asset_path)
                reference_editor_for_snapshot = reference_editor
                reference_snapshot = reference_editor.inspect()
        else:
            reference_snapshot = editor.inspect()
        if suffix == ".xlsx":
            # The compact XLSX view is useful after edits, but the first model
            # request should not spend a turn discovering the exact template
            # range and blank writable cells.
            ranges = [f"{sheet['id']}!{sheet['used_range']}" for sheet in reference_snapshot["sheets"]]
            reference_snapshot = reference_editor_for_snapshot.inspect(node_ids=ranges)
        previewer = previewer or Previewer(output_dir / "previews", config, deadline=deadline)
        if progress:
            progress("生成模板预览" if existing_document is None else "准备原模板对照信息")
        template_pages = previewer.render(task.template_path) if existing_document is None else []
        prep_started = time.monotonic()
        initial_source = source.initial(config.initial_source_chars, primary_refs=task.source_refs)
        if corpus.artifact_manifest:
            initial_source["parse_quality"] = corpus.artifact_manifest["quality"]
        prepared_asset_refs = source.initial_asset_refs(task.source_refs, max_assets=config.initial_source_assets)
        initial_source["prepared_asset_refs"] = prepared_asset_refs
        initial_source["prepared_asset_count"] = len(prepared_asset_refs)
        initial_source["prepared_asset_note"] = "These native source images are attached below; unlisted assets remain available through view_source_asset."
        source_page_paths = []
        if source.source_file.suffix.lower() in (".doc", ".docx", ".pdf") and source.source_file.stat().st_size <= config.initial_source_max_bytes:
            expected = source.document.get("source_checksum")
            if expected and hashlib.sha256(source.source_file.read_bytes()).hexdigest() != expected:
                raise ValueError("Source file changed since DataProxy parsing; cannot prepare matching source pages")
            rendered_source_pages = previewer.render(source.source_file)
            if len(rendered_source_pages) <= config.initial_source_pages:
                source_page_paths = rendered_source_pages
            else:
                initial_source["source_pages_omitted"] = len(rendered_source_pages) - config.initial_source_pages
                source_page_paths = rendered_source_pages[:config.initial_source_pages]
        initial_source["prepared_source_page_count"] = len(source_page_paths)
        initial = dict(instruction=task.instruction, primary_source_refs=list(task.source_refs),
                       source=initial_source, document=reference_snapshot)
        (output_dir / "input.json").write_text(json.dumps(initial, ensure_ascii=False, indent=2))
        parts = [{"type": "text", "text": json.dumps(initial, ensure_ascii=False)}]
        prepared_source_image_paths = []
        for number, path in enumerate(source_page_paths, 1):
            parts += [{"type": "text", "text": f"Prepared source page {number}/{len(source_page_paths)}"}, image_part(path)]
        for ref in prepared_asset_refs:
            path = source.asset_path(ref)
            prepared_source_image_paths.append((ref, path))
            parts += [{"type": "text", "text": f"Prepared source asset {ref}"}, image_part(path)]
        for number, path in enumerate(template_pages, 1):
            parts += [{"type": "text", "text": f"Template page {number}/{len(template_pages)}"}, image_part(path)]
        append_event(trace_path, dict(kind="prepare", elapsed_seconds=round(time.monotonic() - prep_started, 3),
                                     source_page_count=len(source_page_paths), source_asset_count=len(prepared_asset_refs),
                                     template_page_count=len(template_pages), template_format=suffix[1:]))
        messages = [dict(role="system", content=prompt), dict(role="user", content=parts)]
        runtime = ToolRuntime(source, editor, previewer)
        runtime.prepared_source_images = prepared_source_image_paths
        client = client or DoctransaiLLMClient(DoctransaiLLMConfig(env_file=config.env_file,
                model_name=config.model, max_tokens=config.max_output_tokens,
                reasoning_effort=config.reasoning_effort, temperature=config.temperature,
                timeout_seconds=config.llm_timeout_seconds, token_parameter=config.token_parameter))
        diagnostics = None
        if config.model_diagnostics:
            # Local observation only: attaches to the client, records requests,
            # never alters what is sent, retried, or validated.
            from doctransai.llm.diagnostics import ModelDiagnostics
            diagnostics = ModelDiagnostics(output_dir, redact_secrets=[getattr(client, "api_key", "") or ""])
            client.diagnostics = diagnostics
            diagnostics.current_phase = "conversion"
        report["model"] = getattr(client, "model_name", config.model)
        report["llm_settings"] = {key: getattr(client, key, None) for key in
                                  ("model_name", "temperature", "max_tokens", "timeout_seconds", "reasoning_effort", "token_parameter")}
        agent_result = run_agent(client, messages, runtime, config, trace_path, deadline, progress, review_input=initial) if existing_document is None else {}
        if config.review_enabled:
            independent = review_and_repair(source, editor, previewer, initial, client, config, output_dir, deadline, progress)
            if independent["status"] == "passed":
                accepted = independent["rounds"][-1]
                if accepted.get("document_sha256") != hashlib.sha256(editor.output.read_bytes()).hexdigest() or accepted.get("document_version") != editor.version:
                    independent.update(status="incomplete", reason="Document changed after independent review; acceptance invalidated")
            report["independent_semantic_review"] = independent
            result.review_status = "model_passed" if independent["status"] == "passed" else independent["status"]
            report["verification_level"] = "fresh_context_same_model; not human or ground-truth acceptance"
            result.issues.extend(dict(kind="independent_review", message=i["explanation"], targets=i["targets"], review_kind=i["kind"]) for i in independent["issues"])
            if independent["status"] == "incomplete":
                result.issues.append(dict(kind="review_incomplete", message=independent["reason"]))
        else:
            independent = None
            result.review_status = "not_run"
        if hashlib.sha256(task.template_path.read_bytes()).hexdigest() != reference_hash:
            raise ValueError("Original reference template changed during conversion/review")
        unchanged = hashlib.sha256(editor.template.read_bytes()).hexdigest() == editor.original_hash
        with zipfile.ZipFile(editor.template) as before, zipfile.ZipFile(editor.output) as after:
            changed_parts = [n for n in sorted(set(before.namelist()) | set(after.namelist()))
                             if n not in before.namelist() or n not in after.namelist() or before.read(n) != after.read(n)]
        if not unchanged:
            raise ValueError("Template changed during conversion")
        final = output_dir / (("candidate" if config.review_enabled else "result") + suffix)
        os.replace(editor.output, final)
        result.execution_status, result.output_path = "completed", str(final)
        self_check = agent_result.get("editor_self_check", {"issues": [], "missing": []})
        if independent is None:
            result.issues.extend(dict(kind="editor_self_check", message=m) for m in self_check.get("issues", []))
            result.issues.extend(dict(kind=m["kind"], target=m["target"], message=m["message"])
                                 for m in self_check.get("missing", []) if m["kind"] in ("ambiguous", "unsupported"))
            if not editor.applied_batches:
                result.issues.append(dict(kind="no_changes", message="Editor made no changes; confirm that unchanged output is intended"))
            result.review_status = "needs_review" if result.issues else "not_run"
            report["verification_level"] = "editor_self_check_only; not human or ground-truth acceptance"
        if suffix == ".xlsx":
            report["formula_check"] = "Unmodified formulas preserved; copied formulas translated; workbook recalculates on open. No independent cached-value verification."
        if independent is None:
            output_pages = runtime.output_pages
        else:
            last_review = next((r for r in reversed(independent["rounds"]) if r.get("document_version") == editor.version and "output_pages" in r), {})
            output_pages = [Path(p) for p in last_review.get("output_pages", [])]
        report.update(agent_result, template_unchanged=True, reference_template_sha256=reference_hash, changed_package_parts=changed_parts,
                      output_sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
                      output_pages=[str(p) for p in output_pages],
                      delivered_output_pages=last_review.get("pages_checked", []) if independent is not None else sorted(runtime.coverage), document_version=editor.version,
                      structural_check="passed", editor_self_check_completed=bool(agent_result),
                      review_only=existing_document is not None)
    except Exception as exc:
        result.execution_status, result.output_path = "failed", None
        if result.review_status == "model_passed":
            result.review_status = "incomplete"
        draft = editor.output if editor and editor.output.exists() else None
        if draft is None and final is not None and final.exists():
            # A late verification failure must not leave a success-labelled result.
            try:
                os.replace(final, editor.output)
                draft = editor.output
            except OSError:
                draft = final  # Preserve the recoverable file even if renaming fails.
        secret = getattr(client, "api_key", None)
        message = str(exc).replace(secret, "<redacted>") if secret else str(exc)
        issue = dict(kind="execution_error", error_type=type(exc).__name__, message=message[:1500])
        result.issues.append(issue)
        append_event(trace_path, dict(kind="conversion_error", error=issue))
        report["last_preview"] = dict(version=runtime.preview_version if runtime else None,
            pages=[str(p) for p in runtime.output_pages] if runtime else [],
            page_count=len(runtime.output_pages) if runtime and runtime.output_pages else None,
            matches_current_draft=bool(runtime and runtime.preview_version == editor.version))
        report.update(draft_path=str(draft) if draft else None,
                      structural_check="not_completed")
    events = [json.loads(line) for log in sorted(output_dir.glob("*.jsonl")) for line in log.read_text().splitlines()]
    requests = [e for e in events if e.get("kind") in ("model", "model_error")]
    model_events = [e for e in events if e.get("kind") == "model"]
    usage_events = [e.get("usage") for e in model_events if isinstance(e.get("usage"), dict)]
    usage_detail = [u.get("completion_tokens_details", {}) for u in usage_events]
    prompt_detail = [u.get("prompt_tokens_details", {}) for u in usage_events]
    report.update(asdict(result), elapsed_seconds=round(time.monotonic() - started, 3),
                  model_request_count=len(requests),
                  model_request_seconds=sum(e.get("elapsed_seconds", 0) for e in requests),
                  unknown_usage_requests=sum(e.get("usage") is None for e in requests),
                  completed_tool_calls=sum(e.get("kind") == "tool" and e.get("success") is True for e in events),
                  tool_seconds=round(sum(e.get("elapsed_seconds", 0) for e in events if e.get("kind") == "tool"), 3),
                  render_seconds=round(sum(e.get("elapsed_seconds", 0) for e in events if e.get("kind") == "auto_preview"), 3),
                  prepare_seconds=round(sum(e.get("elapsed_seconds", 0) for e in events if e.get("kind") == "prepare"), 3),
                  auto_preview_count=sum(e.get("kind") == "auto_preview" for e in events),
                  input_image_count=sum(e.get("input_image_count", 0) for e in model_events),
                  input_image_chars=sum(e.get("input_image_chars", 0) for e in model_events),
                  prompt_tokens=sum(u.get("prompt_tokens", 0) or 0 for u in usage_events),
                  output_tokens=sum(u.get("completion_tokens", 0) or 0 for u in usage_events),
                  total_tokens=sum(u.get("total_tokens", 0) or 0 for u in usage_events),
                  thinking_tokens=sum(d.get("reasoning_tokens", 0) or 0 for d in usage_detail),
                  image_tokens=sum(d.get("image_tokens", 0) or 0 for d in prompt_detail))
    report_path.write_text(json.dumps(report, default=str, ensure_ascii=False, indent=2))
    if editor is not None:
        try:
            final_snapshot = editor.inspect()
            if isinstance(editor, XlsxEditor):
                final_snapshot = editor.inspect(node_ids=[f"{s['id']}!{s['used_range']}" for s in final_snapshot['sheets']])
            (output_dir / 'audit-final-snapshot.json').write_text(json.dumps(final_snapshot, ensure_ascii=False, default=str))
        except Exception as exc:
            report['audit_snapshot_error'] = type(exc).__name__
            report_path.write_text(json.dumps(report, default=str, ensure_ascii=False, indent=2))
    from doctransai.audit import audit_document
    try:
        audit_document(output_dir, semantic=False)
    except Exception as exc:
        report['audit_ledger_error'] = type(exc).__name__
        report_path.write_text(json.dumps(report, default=str, ensure_ascii=False, indent=2))
    return result


def review_document(task: TaskSpec, document: Path, **kwargs) -> ConversionResult:
    """Review/repair a copy of an existing output against its ORIGINAL template."""
    config = kwargs.pop("config", None)
    if config is None:
        config = RuntimeConfig.from_environment(review_enabled=True)
    elif not config.review_enabled:
        config = replace(config, review_enabled=True)
    return convert(task, config=config, existing_document=document, **kwargs)
