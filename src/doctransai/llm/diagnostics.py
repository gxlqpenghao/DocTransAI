"""Optional local model-request diagnostics.

Off by default. When enabled it only RECORDS what already happens: request
inputs (with Base64 images replaced by hashes/file references), stream event
timings, the provider's actual returned fields (including
``reasoning_content``), usage (unknown stays ``null``, never zero), and
failures with whatever partial data was received. It never changes the
request content, retry, budget, or validation rules, never records
credentials, and never asks the model to re-explain itself.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from doctransai.documents.preview import IMAGE_CONTENT_REGISTRY


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text


_STREAM_EVENT_KEYS = ("first_delta", "reasoning", "content", "tool_args")


class ModelDiagnostics:
    """Append-only local recorder shared by one conversion run."""

    def __init__(self, output_dir: Path, *, redact_secrets: list[str] | None = None):
        self.dir = Path(output_dir)
        self.snapshots_dir = self.dir / "request-snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.dir / "model-diagnostics.jsonl"
        self.redact_secrets = [s for s in (redact_secrets or []) if s]
        self.current_phase: str | None = None
        self._counter = 0
        self.images: dict[str, dict[str, Any]] = {}

    def begin_request(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
                      model: str, stream: bool) -> "RequestRecord":
        self._counter += 1
        return RequestRecord(self, request_id=f"req-{self._counter:04d}", messages=messages,
                             tools=tools, model=model, stream=stream,
                             phase=self.current_phase)

    def _append(self, record: dict[str, Any]) -> None:
        try:
            with self.log_path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Diagnostics must never break a conversion.

    def _image_ref(self, url: str, position: dict[str, int]) -> dict[str, Any]:
        ref: dict[str, Any] = {"type": "image_url_redacted",
                               "data_url_prefix": url.split(",", 1)[0] if "," in url else url[:40]}
        payload = url.split(",", 1)[1] if "," in url else ""
        digest = None
        if payload:
            try:
                raw = base64.b64decode(payload, validate=False)
                digest = hashlib.sha256(raw).hexdigest()
                ref["sha256"] = digest
                ref["bytes"] = len(raw)
            except Exception:
                ref["sha256"] = None
                ref["bytes"] = None
                ref["decode_error"] = True
        else:
            ref["sha256"] = None
            ref["bytes"] = 0
        if digest:
            entry = self.images.setdefault(digest, dict(sha256=digest, first_seen=position,
                                                        likely_path=None, seen_count=0))
            entry["seen_count"] += 1
            likely = IMAGE_CONTENT_REGISTRY.get(digest)
            if likely and not entry["likely_path"]:
                entry["likely_path"] = likely
            ref["likely_path"] = likely
        return ref

    def snapshot_messages(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        image_count = 0
        snapshot: list[dict[str, Any]] = []
        for message_index, message in enumerate(messages):
            item = dict(message)
            content = message.get("content")
            if isinstance(content, list):
                parts: list[Any] = []
                for part_index, part in enumerate(content):
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        url = (part.get("image_url") or {}).get("url", "")
                        parts.append(self._image_ref(url, dict(message_index=message_index,
                                                               part_index=part_index)))
                        image_count += 1
                    else:
                        parts.append(part)
                item["content"] = parts
            snapshot.append(item)
        return snapshot, image_count

    def flush_image_manifest(self) -> None:
        if not self.images:
            return
        try:
            (self.dir / "images-manifest.json").write_text(
                json.dumps(self.images, ensure_ascii=False, indent=2))
        except Exception:
            pass


class RequestRecord:
    """One model request: snapshot written before sending; record closed at end."""

    def __init__(self, diagnostics: ModelDiagnostics, *, request_id: str,
                 messages: list[dict[str, Any]], tools: list[dict[str, Any]],
                 model: str, stream: bool, phase: str | None):
        self.d = diagnostics
        self.request_id = request_id
        self.started_at = _now()
        self.snapshot_file: str | None = f"{request_id}-input.json"
        self.snapshot_error: str | None = None
        self.image_part_count = 0
        self.stream_times: dict[str, str] = {}
        self.response: dict[str, Any] | None = None
        self.usage: dict[str, Any] | None = None
        self.error: dict[str, Any] | None = None
        try:
            snap_messages, self.image_part_count = diagnostics.snapshot_messages(messages)
            payload = dict(request_id=request_id, phase=phase, model=model, stream=stream,
                           message_count=len(messages), image_part_count=self.image_part_count,
                           tools_sha256=hashlib.sha256(
                               json.dumps(tools, sort_keys=True).encode()).hexdigest(),
                           messages=snap_messages)
            (diagnostics.snapshots_dir / self.snapshot_file).write_text(
                json.dumps(payload, ensure_ascii=False, indent=1))
        except Exception as exc:
            self.snapshot_file = None
            self.snapshot_error = str(exc)[:300]

    def mark_stream_event(self, kind: str) -> None:
        self.stream_times.setdefault(kind, _now())

    def complete(self, *, message: dict[str, Any], usage: dict[str, Any] | None,
                 model: str | None) -> None:
        self.response = {key: message.get(key) for key in
                         ("role", "content", "reasoning_content", "tool_calls")}
        self.usage = usage if isinstance(usage, dict) else None
        self._finalize(status="ok", model=model)

    def fail(self, exc: BaseException, *, partial_message: dict[str, Any] | None = None,
             partial_usage: dict[str, Any] | None = None) -> None:
        self.error = dict(error_type=type(exc).__name__,
                          message=_redact(str(exc)[:1200], self.d.redact_secrets))
        if partial_message is not None:
            partial = {key: partial_message.get(key) for key in
                       ("role", "content", "reasoning_content", "tool_calls")}
            if any(value for value in partial.values() if isinstance(value, (str, list))):
                self.response = partial
        if isinstance(partial_usage, dict):
            self.usage = partial_usage
        try:
            exc.diagnostics_request_id = self.request_id  # correlation for callers
        except Exception:
            pass
        self._finalize(status="error", model=None)

    def _finalize(self, *, status: str, model: str | None) -> None:
        if getattr(self, "_closed", False):
            return  # Inner handlers may already have failed this request.
        self._closed = True
        usage = self.usage if isinstance(self.usage, dict) else None
        prompt_details = (usage or {}).get("prompt_tokens_details") or {}
        completion_details = (usage or {}).get("completion_tokens_details") or {}

        def num(value: Any) -> float | int | None:
            # Unknown must stay unknown; zero is a measurement, not a default.
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

        record = dict(
            kind="model_request",
            request_id=self.request_id,
            status=status,
            incomplete=status != "ok",
            started_at=self.started_at,
            ended_at=_now(),
            snapshot_file=self.snapshot_file,
            snapshot_error=self.snapshot_error,
            stream_first_event_times={key: self.stream_times.get(key) for key in _STREAM_EVENT_KEYS},
            response=self.response,
            usage_raw=usage,
            usage_normalized=dict(
                input_tokens=num((usage or {}).get("prompt_tokens")),
                output_tokens=num((usage or {}).get("completion_tokens")),
                reasoning_tokens=num(completion_details.get("reasoning_tokens")),
                cached_tokens=num(prompt_details.get("cached_tokens")),
                image_tokens=num(prompt_details.get("image_tokens")),
            ),
            model=model,
            error=self.error,
        )
        self.d._append(record)
        self.d.flush_image_manifest()
