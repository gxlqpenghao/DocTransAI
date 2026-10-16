"""One bounded tool loop. It does not know document fields or business roles."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time

import httpx
from jsonschema import ValidationError

from doctransai.documents.preview import image_part


def append_event(path: Path, event: dict):
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat(), **event), ensure_ascii=False) + "\n")


def _image_metrics(messages):
    count = 0
    chars = 0
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                count += 1
                url = part.get("image_url", {}).get("url", "")
                chars += len(url) if isinstance(url, str) else 0
    return count, chars


def _checkpoint_after_preview(runtime, review_input, system_message, trace_path, step, config, *, auto=False):
    """Create the next model context from a real current-version preview."""
    page_count = len(runtime.output_pages)
    delivered = min(page_count, config.auto_preview_max_pages)
    runtime.coverage = set(range(1, delivered + 1))
    all_pages_delivered = delivered == page_count
    context = dict(phase="result_check", instruction=review_input.get("instruction"),
                   primary_source_refs=review_input["primary_source_refs"], source=review_input["source"],
                   original_template=review_input["document"], current_document=runtime.editor.inspect(),
                   preview_receipt=dict(tool="program_auto_preview" if auto else "preview_document",
                                        version=runtime.editor.version,
                                        delivered_pages=sorted(runtime.coverage),
                                        all_pages_delivered=all_pages_delivered,
                                        missing_pages=sorted(set(range(1, page_count + 1)) - runtime.coverage)))
    instruction = (
        "程序已经对当前版本真实渲染并附上输出页。先检查这些当前页；不要再次调用preview_document索取已经附带的同一版本页面。"
        "如果没有明确问题，直接finish并如实记录missing/ambiguity；如果有明确、局部且有依据的问题，只做一批有限修正，程序会自动重新渲染。"
        if auto else
        "下面是刚才成功获取的当前输出页。检查这些图；无修改时直接finish，只有发现明确问题才局部修改。"
    )
    if not all_pages_delivered:
        instruction += f" 当前只附带前{delivered}页；finish前必须用preview_document读取缺失页：{sorted(set(range(1, page_count + 1)) - runtime.coverage)}。"
    parts = [{"type": "text", "text": instruction + "\n" + json.dumps(context, ensure_ascii=False)}]
    for ref, path in getattr(runtime, "prepared_source_images", []):
        parts += [{"type": "text", "text": f"Prepared source asset {ref} (for factual/image comparison)"}, image_part(path)]
    for number, path in enumerate(runtime.output_pages[:delivered], 1):
        parts += [{"type": "text", "text": f"Current output page {number}/{page_count}"}, image_part(path)]
    runtime.preview_version = runtime.editor.version
    runtime.preview_round = step
    append_event(trace_path, dict(kind="review_checkpoint", step=step, version=runtime.preview_version,
                                 output_image_count=delivered, page_count=page_count,
                                 earlier_images_omitted=not all_pages_delivered, automatic=auto))
    return [system_message, dict(role="user", content=parts)]


def run_agent(client, messages, runtime, config, trace_path: Path, deadline: float, progress=None, review_input=None):
    calls = []
    system_message = messages[0]
    checkpoint_version = -1
    for step in range(1, config.max_steps + 1):
        if time.monotonic() >= deadline:
            raise TimeoutError("Conversion time budget exhausted")
        runtime.round = step
        if progress:
            progress(f"模型步骤 {step}/{config.max_steps}")
        for attempt in range(2):
            start = time.monotonic()
            try:
                response = client.chat(messages, runtime.tools, stream=True, deadline=deadline)
                break
            except Exception as exc:
                # Retrying a request is safe before ANY returned tool is executed.
                # Prior successful edits stay in messages; they are not replayed.
                secret = getattr(client, "api_key", None)
                detail = str(exc).replace(secret, "<redacted>") if secret else str(exc)
                append_event(trace_path, dict(kind="model_error", step=step, attempt=attempt + 1,
                    error_type=type(exc).__name__, message=detail[:1200],
                    elapsed_seconds=round(time.monotonic() - start, 3), usage=None))
                if time.monotonic() >= deadline:
                    raise TimeoutError("Conversion time budget exhausted while waiting for the model; draft retained") from exc
                status = getattr(exc, "status_code", 0)
                retryable = isinstance(exc, httpx.TransportError) or getattr(exc, "retryable", False) or status == 429 or 500 <= status < 600
                if attempt or not retryable:
                    raise
                if progress:
                    progress("临时模型请求失败；重试本次请求一次，不重放文档操作")
                time.sleep(.5)
        message = response["message"]
        image_count, image_chars = _image_metrics(messages)
        append_event(trace_path, dict(kind="model", step=step, model=response.get("model"), usage=response.get("usage"),
                                     elapsed_seconds=round(time.monotonic() - start, 3),
                                     input_image_count=image_count, input_image_chars=image_chars,
                                     diagnostics_request_id=response.get("_diagnostics_request_id"),
                                     message={k: v for k, v in message.items() if k != "reasoning_content"}))
        calls.append(response.get("usage"))
        messages.append(message)
        tool_calls = message.get("tool_calls") or []
        pending_images = []
        edited = False
        if len(tool_calls) > 40 or len({c.get("id") for c in tool_calls}) != len(tool_calls):
            raise ValueError("Invalid/oversized tool call batch")
        for call in tool_calls:
            name = call["function"]["name"]
            if progress:
                progress(f"工具：{name}")
            tool_exception = None
            args = None
            tool_started = time.monotonic()
            version_before = runtime.editor.version
            try:
                args = json.loads(call["function"]["arguments"])
                result, images = runtime.invoke(name, args)
                pending_images.extend(images)
                successful = True
                edited = edited or (name == "edit_document" and runtime.editor.version != version_before)
            except ValidationError as exc:
                location = "/".join(str(p) for p in exc.absolute_path) or "root"
                result, images, successful = dict(error="ValidationError", message=f"Invalid arguments at {location} ({exc.validator}): {exc.message[:700]}"), [], False
            except (ValueError, KeyError, TypeError, OSError) as exc:
                tool_exception = exc
                result, images, successful = dict(error=type(exc).__name__, message=str(exc)[:1500]), [], False
            except Exception as exc:
                # JSON Schema errors and renderer errors are recoverable tool feedback,
                # but never expose a giant schema or image payload in the transcript.
                result, images, successful = dict(error=type(exc).__name__, message=str(exc)[:1000]), [], False
            if name == "edit_document":
                result.update(input_version=version_before, output_version=runtime.editor.version,
                              rolled_back=not successful and runtime.editor.version == version_before)
                if not successful:
                    result.update(getattr(tool_exception, "edit_failure", {}))
            append_event(trace_path, dict(kind="tool", step=step, name=name, arguments=args,
                                         success=successful, result=result,
                                         delivered_image_count=sum(p.get("type") == "image_url" for p in images),
                                         elapsed_seconds=round(time.monotonic() - tool_started, 3),
                                         output_version=runtime.editor.version))
            messages.append(dict(role="tool", tool_call_id=call["id"], content=json.dumps(result, ensure_ascii=False)))
        if pending_images:
            messages.append(dict(role="user", content=[{"type": "text", "text": "Inspect these actual images before your next action."}, *pending_images]))
        if review_input is not None and edited:
            render_started = time.monotonic()
            if runtime.preview_version != runtime.editor.version:
                runtime.output_pages = runtime.previewer.render(runtime.editor.output)
            append_event(trace_path, dict(kind="auto_preview", step=step, version=runtime.editor.version,
                                         page_count=len(runtime.output_pages),
                                         page_files=[str(p) for p in runtime.output_pages],
                                         elapsed_seconds=round(time.monotonic() - render_started, 3)))
            messages = _checkpoint_after_preview(runtime, review_input, system_message, trace_path, step, config, auto=True)
            checkpoint_version = runtime.editor.version
        elif (review_input is not None and runtime.preview_round == step and
                runtime.preview_version == runtime.editor.version and
                runtime.coverage == set(range(1, len(runtime.output_pages) + 1)) and len(runtime.output_pages) <= 4):
            # A small final document does not need all earlier source-page images,
            # tool-selection deliberation and obsolete snapshots on every review call.
            messages = _checkpoint_after_preview(runtime, review_input, system_message, trace_path, step, config, auto=False)
            checkpoint_version = runtime.editor.version
        if runtime.finished is not None:
            return dict(steps=step, usage=calls, **{getattr(runtime, "result_key", "editor_self_check"): runtime.finished})
        if not tool_calls:
            messages.append(dict(role="user", content="Use the available tools to complete this phase and submit its required structured completion. A prose answer alone does not complete the phase."))
    raise RuntimeError(f"Step budget exhausted ({config.max_steps}); partial working document retained")
