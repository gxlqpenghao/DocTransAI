"""Public single-document entrypoint for the new tool path."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import time
import zipfile

from doctransai.agent import append_event, run_agent
from doctransai.config import RuntimeConfig
from doctransai.data_layer import read_parsed_document_bundle
from doctransai.data_layer.view import SourceView
from doctransai.documents.docx import DocxEditor
from doctransai.documents.xlsx import XlsxEditor
from doctransai.documents.preview import Previewer, image_part
from doctransai.llm.client import DoctransaiLLMClient, DoctransaiLLMConfig
from doctransai.tools import tools_for_format, ToolRuntime
from doctransai.types import ConversionResult, TaskSpec


def convert(task: TaskSpec, *, config: RuntimeConfig | None = None, client=None, previewer=None,
            progress=None) -> ConversionResult:
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
    report = dict(task=asdict(task), model=config.model, independent_semantic_review="not_run")
    editor = None
    try:
        if not task.instruction.strip():
            raise ValueError("A conversion instruction is required")
        suffix = task.template_path.suffix.lower()
        if suffix not in (".docx", ".xlsx"):
            raise ValueError("Targets must be DOCX or XLSX; legacy templates need explicit materialization first")
        tools = tools_for_format(suffix[1:])
        prompt = (Path(__file__).parent / "prompts/document_editing_policy.md").read_text()
        (output_dir / "task.json").write_text(json.dumps(dict(task=asdict(task), config=asdict(config),
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            tools_sha256=hashlib.sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest()), default=str, ensure_ascii=False, indent=2))
        if progress:
            progress("读取DataProxy原生材料")
        corpus = read_parsed_document_bundle(task.bundle_path)
        source = SourceView(corpus, document_id=task.document_id, source_file=task.source_file)
        source.check_refs(task.source_refs)
        editor = (XlsxEditor if suffix == ".xlsx" else DocxEditor)(task.template_path, output_dir / ("working" + suffix), source.asset_path)
        previewer = previewer or Previewer(output_dir / "previews", config, deadline=deadline)
        if progress:
            progress("生成模板预览")
        template_pages = previewer.render(editor.template)
        initial = dict(instruction=task.instruction, primary_source_refs=list(task.source_refs),
                       source=source.initial(config.initial_source_chars), document=editor.inspect())
        (output_dir / "input.json").write_text(json.dumps(initial, ensure_ascii=False, indent=2))
        parts = [{"type": "text", "text": json.dumps(initial, ensure_ascii=False)}]
        for number, path in enumerate(template_pages, 1):
            parts += [{"type": "text", "text": f"Template page {number}/{len(template_pages)}"}, image_part(path)]
        messages = [dict(role="system", content=prompt), dict(role="user", content=parts)]
        runtime = ToolRuntime(source, editor, previewer)
        client = client or DoctransaiLLMClient(DoctransaiLLMConfig(env_file=config.env_file,
                model_name=config.model, max_tokens=config.max_output_tokens))
        report["model"] = getattr(client, "model_name", config.model)
        report["llm_settings"] = {key: getattr(client, key, None) for key in
                                  ("model_name", "temperature", "max_tokens", "timeout_seconds")}
        agent_result = run_agent(client, messages, runtime, config, trace_path, deadline, progress, review_input=initial)
        unchanged = hashlib.sha256(editor.template.read_bytes()).hexdigest() == editor.original_hash
        with zipfile.ZipFile(editor.template) as before, zipfile.ZipFile(editor.output) as after:
            changed_parts = [n for n in sorted(set(before.namelist()) | set(after.namelist()))
                             if n not in before.namelist() or n not in after.namelist() or before.read(n) != after.read(n)]
        if not unchanged:
            raise ValueError("Template changed during conversion")
        final = output_dir / ("result" + suffix)
        os.replace(editor.output, final)
        result.execution_status, result.output_path = "completed", str(final)
        self_check = agent_result["editor_self_check"]
        result.issues.extend(dict(kind="editor_self_check", message=m) for m in self_check["issues"])
        result.issues.extend(dict(kind=m["kind"], target=m["target"], message=m["message"])
                             for m in self_check["missing"] if m["kind"] in ("ambiguous", "unsupported"))
        if not editor.applied_batches:
            result.issues.append(dict(kind="no_changes", message="Editor made no changes; confirm that unchanged output is intended"))
        needs_review = bool(result.issues)
        # An editor's own finish response is not independent review.
        result.review_status = "needs_review" if needs_review else "not_run"
        if suffix == ".xlsx":
            report["formula_check"] = "Unmodified formulas preserved; copied formulas translated; workbook recalculates on open. No independent cached-value verification."
        report.update(agent_result, template_unchanged=True, changed_package_parts=changed_parts,
                      output_sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
                      output_pages=[str(p) for p in runtime.output_pages],
                      delivered_output_pages=sorted(runtime.coverage), document_version=editor.version,
                      structural_check="passed", editor_self_check_completed=True)
    except Exception as exc:
        secret = getattr(client, "api_key", None)
        message = str(exc).replace(secret, "<redacted>") if secret else str(exc)
        issue = dict(kind="execution_error", error_type=type(exc).__name__, message=message[:1500])
        result.issues.append(issue)
        append_event(trace_path, dict(kind="conversion_error", error=issue))
        report.update(draft_path=str(editor.output) if editor and editor.output.exists() else None,
                      structural_check="not_completed")
    events = [json.loads(line) for line in trace_path.read_text().splitlines()] if trace_path.exists() else []
    requests = [e for e in events if e.get("kind") in ("model", "model_error")]
    report.update(asdict(result), elapsed_seconds=round(time.monotonic() - started, 3),
                  model_request_count=len(requests),
                  model_request_seconds=sum(e.get("elapsed_seconds", 0) for e in requests),
                  unknown_usage_requests=sum(e.get("usage") is None for e in requests),
                  completed_tool_calls=sum(e.get("kind") == "tool" and e.get("success") is True for e in events))
    report_path.write_text(json.dumps(report, default=str, ensure_ascii=False, indent=2))
    return result
