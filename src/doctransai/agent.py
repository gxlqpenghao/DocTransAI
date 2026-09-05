"""One bounded tool loop. It does not know document fields or business roles."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time

import httpx

from doctransai.tools import TOOLS
from doctransai.documents.preview import image_part


def append_event(path: Path, event: dict):
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat(), **event), ensure_ascii=False) + "\n")


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
                response = client.chat(messages, TOOLS, stream=True, deadline=deadline)
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
        append_event(trace_path, dict(kind="model", step=step, model=response.get("model"), usage=response.get("usage"),
                                     elapsed_seconds=round(time.monotonic() - start, 3),
                                     message={k: v for k, v in message.items() if k != "reasoning_content"}))
        calls.append(response.get("usage"))
        messages.append(message)
        tool_calls = message.get("tool_calls") or []
        pending_images = []
        if len(tool_calls) > 40 or len({c.get("id") for c in tool_calls}) != len(tool_calls):
            raise ValueError("Invalid/oversized tool call batch")
        for call in tool_calls:
            name = call["function"]["name"]
            if progress:
                progress(f"工具：{name}")
            args = None
            try:
                if runtime.finished is not None:
                    raise ValueError("finish must be the last operation")
                args = json.loads(call["function"]["arguments"])
                result, images = runtime.invoke(name, args)
                pending_images.extend(images)
                successful = True
            except (ValueError, KeyError, TypeError, OSError) as exc:
                result, images, successful = dict(error=type(exc).__name__, message=str(exc)[:1500]), [], False
            except Exception as exc:
                # JSON Schema errors and renderer errors are recoverable tool feedback,
                # but never expose a giant schema or image payload in the transcript.
                result, images, successful = dict(error=type(exc).__name__, message=str(exc)[:1000]), [], False
            append_event(trace_path, dict(kind="tool", step=step, name=name, arguments=args,
                                         success=successful, result=result,
                                         delivered_image_count=sum(p.get("type") == "image_url" for p in images),
                                         output_version=runtime.editor.version))
            messages.append(dict(role="tool", tool_call_id=call["id"], content=json.dumps(result, ensure_ascii=False)))
        if pending_images:
            messages.append(dict(role="user", content=[{"type": "text", "text": "Inspect these actual images before your next action."}, *pending_images]))
        if (review_input is not None and runtime.preview_round == step and
                runtime.preview_version == runtime.editor.version and checkpoint_version != runtime.editor.version and
                runtime.coverage == set(range(1, len(runtime.output_pages) + 1)) and len(runtime.output_pages) <= 4):
            # A small final document does not need all earlier source-page images,
            # tool-selection deliberation and obsolete snapshots on every review call.
            context = dict(phase="result_check", instruction=review_input["instruction"],
                           primary_source_refs=review_input["primary_source_refs"], source=review_input["source"],
                           original_template=review_input["document"], current_document=runtime.editor.inspect(),
                           preview_receipt=dict(tool="preview_document", version=runtime.editor.version,
                                                delivered_pages=sorted(runtime.coverage), all_pages_delivered=True))
            parts = [{"type": "text", "text": "进入当前输出的结果检查，不重新生成已有正确内容。下面的输出图来自刚才已成功执行的preview_document，当前版本全部页已经提供；检查这些图即可，无修改时可直接finish，不必为形式重复预览。下方保留原生材料、原模板结构与当前文档。先前源图对话未继续附带，需要时可重新取源图或preview_document(target=template)。有问题仅局部修改后重新预览。\n" + json.dumps(context, ensure_ascii=False)}]
            for number, path in enumerate(runtime.output_pages, 1):
                parts += [{"type": "text", "text": f"Current output page {number}"}, image_part(path)]
            messages = [system_message, dict(role="user", content=parts)]
            checkpoint_version = runtime.editor.version
            append_event(trace_path, dict(kind="review_checkpoint", step=step, version=checkpoint_version,
                                         output_image_count=len(runtime.output_pages), earlier_images_omitted=True))
        if runtime.finished is not None:
            return dict(steps=step, usage=calls, editor_self_check=runtime.finished)
        if not tool_calls:
            messages.append(dict(role="user", content="Use the available tools to complete the document, then preview all output pages and finish. A prose answer alone does not edit the file."))
    raise RuntimeError(f"Step budget exhausted ({config.max_steps}); partial working document retained")
