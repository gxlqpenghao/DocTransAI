from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


DOCTRANSAI_LLM_API_KEY_ENV = "DOCTRANSAI_LLM_API_KEY"
DOCTRANSAI_LLM_BASE_URL_ENV = "DOCTRANSAI_LLM_BASE_URL"
DOCTRANSAI_LLM_MODEL_ENV = "DOCTRANSAI_LLM_MODEL"
DOCTRANSAI_LLM_TIMEOUT_SECONDS_ENV = "DOCTRANSAI_LLM_TIMEOUT_SECONDS"
DOCTRANSAI_LLM_MAX_TOKENS_ENV = "DOCTRANSAI_LLM_MAX_TOKENS"
DOCTRANSAI_LLM_TEMPERATURE_ENV = "DOCTRANSAI_LLM_TEMPERATURE"
DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV = "DOCTRANSAI_LLM_MAX_REQUEST_BYTES"
DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV = "DOCTRANSAI_LLM_MAX_INPUT_CHARS"
DOCTRANSAI_DATAPROXY_ROOT_ENV = "DOCTRANSAI_DATAPROXY_ROOT"

DEFAULT_DOCTRANSAI_LLM_MODEL = "kimi-k3"
DEFAULT_DOCTRANSAI_LLM_MAX_REQUEST_BYTES = 6_000_000
DEFAULT_DOCTRANSAI_LLM_MAX_INPUT_CHARS = 0


def _default_temperature(model: str) -> float:
    # Match the provider's K3 default; do not carry over the legacy zero setting.
    return 1.0 if model.split("/")[-1] == "kimi-k3" else 0.0

_FALLBACK_API_KEY_ENV = "DATAPROXY_QWEN_API_KEY"
_FALLBACK_BASE_URL_ENV = "DATAPROXY_QWEN_BASE_URL"


class DoctransaiLLMConfigurationError(ValueError):
    pass


class DoctransaiLLMResponseError(ValueError):
    """An incomplete/invalid response must never reach the tool executor."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class DoctransaiLLMHTTPStatusError(RuntimeError):
    def __init__(self, *, status_code: int, url: str, response_text: str) -> None:
        self.status_code = status_code
        self.url = url
        self.response_text = response_text
        super().__init__(
            f"LLM request failed with HTTP {status_code} for {url}. Response body: {response_text}"
        )


class DoctransaiLLMRequestTooLargeError(RuntimeError):
    def __init__(self, *, estimated_request_bytes: int, max_request_body_bytes: int) -> None:
        self.estimated_request_bytes = estimated_request_bytes
        self.max_request_body_bytes = max_request_body_bytes
        super().__init__(
            "LLM request body estimate "
            f"{estimated_request_bytes} bytes exceeds configured maximum {max_request_body_bytes} bytes."
        )


class DoctransaiLLMInputTooLargeError(RuntimeError):
    def __init__(self, *, estimated_input_chars: int, max_input_chars: int) -> None:
        self.estimated_input_chars = estimated_input_chars
        self.max_input_chars = max_input_chars
        super().__init__(
            "LLM input estimate "
            f"{estimated_input_chars} chars exceeds configured maximum {max_input_chars} chars."
        )


@dataclass(frozen=True, slots=True)
class DoctransaiLLMConfig:
    api_key: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    timeout_seconds: float | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    max_request_body_bytes: int | None = None
    max_input_chars: int | None = None
    transport: httpx.BaseTransport | None = None
    env_file: Path | None = None


class DoctransaiLLMClient:
    def __init__(self, config: DoctransaiLLMConfig | None = None) -> None:
        resolved = config or DoctransaiLLMConfig()
        file_fallbacks = _load_dataproxy_env_fallbacks(resolved.env_file)
        self.api_key = _resolve_string(
            resolved.api_key,
            DOCTRANSAI_LLM_API_KEY_ENV,
            _FALLBACK_API_KEY_ENV,
            file_fallbacks=file_fallbacks,
        )
        self.base_url = _resolve_string(
            resolved.base_url,
            DOCTRANSAI_LLM_BASE_URL_ENV,
            _FALLBACK_BASE_URL_ENV,
            file_fallbacks=file_fallbacks,
        )
        self.model_name = resolved.model_name or os.environ.get(DOCTRANSAI_LLM_MODEL_ENV) or file_fallbacks.get(DOCTRANSAI_LLM_MODEL_ENV) or DEFAULT_DOCTRANSAI_LLM_MODEL
        self.timeout_seconds = _resolve_float(
            resolved.timeout_seconds,
            DOCTRANSAI_LLM_TIMEOUT_SECONDS_ENV,
            None,
            default=180.0,
            file_fallbacks=file_fallbacks,
        )
        self.max_tokens = _resolve_int(
            resolved.max_tokens,
            DOCTRANSAI_LLM_MAX_TOKENS_ENV,
            None,
            default=8192,
            file_fallbacks=file_fallbacks,
        )
        self.temperature = _resolve_float(
            resolved.temperature,
            DOCTRANSAI_LLM_TEMPERATURE_ENV,
            None,
            default=_default_temperature(self.model_name),
            file_fallbacks=file_fallbacks,
        )
        self.max_request_body_bytes = resolve_llm_request_body_limit_bytes(
            resolved.max_request_body_bytes,
            file_fallbacks=file_fallbacks,
        )
        self.max_input_chars = resolve_llm_input_char_limit(
            resolved.max_input_chars,
            file_fallbacks=file_fallbacks,
        )
        self.transport = resolved.transport

        if not self.api_key:
            raise DoctransaiLLMConfigurationError(
                f"LLM API key is not configured. Set `{DOCTRANSAI_LLM_API_KEY_ENV}` or `{_FALLBACK_API_KEY_ENV}`."
            )
        if not self.base_url:
            raise DoctransaiLLMConfigurationError(
                f"LLM base URL is not configured. Set `{DOCTRANSAI_LLM_BASE_URL_ENV}` or `{_FALLBACK_BASE_URL_ENV}`."
            )

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        user_parts: list[dict[str, Any]] | None = None,
    ) -> str:
        payload = build_chat_completions_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            user_parts=user_parts,
            model_name=self.model_name,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        estimated_request_bytes = estimate_request_body_bytes(payload)
        if (
            self.max_request_body_bytes is not None
            and estimated_request_bytes > self.max_request_body_bytes
        ):
            raise DoctransaiLLMRequestTooLargeError(
                estimated_request_bytes=estimated_request_bytes,
                max_request_body_bytes=self.max_request_body_bytes,
            )
        estimated_input_chars = estimate_chat_input_chars(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            user_parts=user_parts,
        )
        if self.max_input_chars is not None and estimated_input_chars > self.max_input_chars:
            raise DoctransaiLLMInputTooLargeError(
                estimated_input_chars=estimated_input_chars,
                max_input_chars=self.max_input_chars,
            )

        with httpx.Client(
            base_url=self.base_url.rstrip("/"),
            timeout=self.timeout_seconds,
            transport=self.transport,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        ) as client:
            response = client.post("/chat/completions", json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise DoctransaiLLMHTTPStatusError(
                    status_code=exc.response.status_code,
                    url=str(exc.request.url),
                    response_text=_response_text_preview(exc.response),
                ) from exc
            body = response.json()

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DoctransaiLLMConfigurationError("LLM response is missing choices.")
        first_choice = next((item for item in choices if isinstance(item, dict)), {})
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise DoctransaiLLMConfigurationError("LLM response is missing message payload.")
        content = message.get("content")
        if not isinstance(content, str):
            raise DoctransaiLLMConfigurationError("LLM response content is missing or not text.")
        return content

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *,
             stream: bool = True, deadline: float | None = None) -> dict[str, Any]:
        """One model request. No automatic retries or tool execution here."""
        payload = dict(model=self.model_name, messages=messages, tools=tools,
                       tool_choice="auto", temperature=self.temperature, max_tokens=self.max_tokens,
                       stream=stream)
        if stream:
            payload["stream_options"] = {"include_usage": True}
        size = estimate_request_body_bytes(payload)
        if self.max_request_body_bytes is not None and size > self.max_request_body_bytes:
            raise DoctransaiLLMRequestTooLargeError(estimated_request_bytes=size, max_request_body_bytes=self.max_request_body_bytes)
        chars = sum(_input_content_char_count(m.get("content")) for m in messages) + len(json.dumps(tools))
        if self.max_input_chars is not None and chars > self.max_input_chars:
            raise DoctransaiLLMInputTooLargeError(estimated_input_chars=chars, max_input_chars=self.max_input_chars)
        remaining = self.timeout_seconds if deadline is None else min(self.timeout_seconds, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Conversion time budget exhausted before model request")
        with httpx.Client(base_url=self.base_url.rstrip("/"), timeout=remaining, transport=self.transport,
                          headers={"Authorization": f"Bearer {self.api_key}"}) as client:
            with client.stream("POST", "/chat/completions", json=payload) as response:
                if response.is_error:
                    response.read()
                    raise DoctransaiLLMHTTPStatusError(status_code=response.status_code,
                        url=str(response.request.url), response_text=_response_text_preview(response))
                if not stream:
                    response.read()
                    body = response.json()
                    choice = body.get("choices", [{}])[0]
                    if choice.get("finish_reason") not in ("stop", "tool_calls"):
                        raise DoctransaiLLMResponseError("Incomplete model response")
                    message = choice.get("message", {})
                    if message.get("role") != "assistant":
                        raise DoctransaiLLMResponseError("Missing assistant message")
                    return dict(message=message, usage=body.get("usage"), model=body.get("model", self.model_name))
                message: dict[str, Any] = {"role": "assistant", "content": ""}
                calls: dict[int, dict[str, Any]] = {}
                usage, finish_reason, done = None, None, False
                returned_model = self.model_name
                for line in response.iter_lines():
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TimeoutError("Conversion time budget exhausted during model stream")
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        done = True
                        break
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise DoctransaiLLMResponseError("Invalid stream event") from exc
                    if "error" in event:
                        error = event["error"]
                        code = str(error.get("code", "unknown")) if isinstance(error, dict) else "unknown"
                        detail = str(error.get("message", "")) if isinstance(error, dict) else str(error)
                        detail = detail.replace(self.api_key, "<redacted>")[:800]
                        transient = code.startswith(("InternalError", "ServiceUnavailable", "Throttling"))
                        raise DoctransaiLLMResponseError(f"Provider stream error {code}: {detail}", retryable=transient)
                    returned_model = event.get("model", returned_model)
                    if event.get("usage") is not None:
                        usage = event["usage"]
                    for choice in event.get("choices", []):
                        if choice.get("index", 0) != 0:
                            continue
                        finish_reason = choice.get("finish_reason") or finish_reason
                        delta = choice.get("delta", {})
                        for key in ("content", "reasoning_content"):
                            if delta.get(key):
                                message[key] = message.get(key, "") + delta[key]
                        for fragment in delta.get("tool_calls", []):
                            call = calls.setdefault(fragment["index"], {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if fragment.get("id"):
                                call["id"] = fragment["id"]
                            for key in ("name", "arguments"):
                                call["function"][key] += fragment.get("function", {}).get(key) or ""
                if not done or finish_reason not in ("stop", "tool_calls"):
                    raise DoctransaiLLMResponseError(f"Incomplete model stream (finish_reason={finish_reason!r})")
                if calls:
                    message["tool_calls"] = [calls[k] for k in sorted(calls)]
                    if any(not c["id"] or not c["function"]["name"] for c in calls.values()):
                        raise DoctransaiLLMResponseError("Incomplete tool call identity")
                return dict(message=message, usage=usage, model=returned_model)


def generate_text_with_doctransai_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    user_parts: list[dict[str, Any]] | None = None,
    config: DoctransaiLLMConfig | None = None,
) -> str:
    return DoctransaiLLMClient(config).generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        user_parts=user_parts,
    )


def build_chat_completions_payload(
    *,
    system_prompt: str,
    user_prompt: str,
    user_parts: list[dict[str, Any]] | None = None,
    model_name: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    return {
        "model": model_name or os.environ.get(DOCTRANSAI_LLM_MODEL_ENV) or DEFAULT_DOCTRANSAI_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_parts if user_parts is not None else user_prompt},
        ],
        "max_tokens": max_tokens if max_tokens is not None else _resolve_int(
            None,
            DOCTRANSAI_LLM_MAX_TOKENS_ENV,
            None,
            default=8192,
        ),
        "temperature": temperature if temperature is not None else _resolve_float(
            None,
            DOCTRANSAI_LLM_TEMPERATURE_ENV,
            None,
            default=_default_temperature(model_name or os.environ.get(DOCTRANSAI_LLM_MODEL_ENV) or DEFAULT_DOCTRANSAI_LLM_MODEL),
        ),
    }


def estimate_request_body_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def estimate_chat_request_bytes(
    *,
    system_prompt: str,
    user_prompt: str,
    user_parts: list[dict[str, Any]] | None = None,
) -> int:
    return estimate_request_body_bytes(
        build_chat_completions_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            user_parts=user_parts,
        )
    )


def estimate_chat_input_chars(
    *,
    system_prompt: str,
    user_prompt: str,
    user_parts: list[dict[str, Any]] | None = None,
) -> int:
    user_content_chars = (
        _input_content_char_count(user_parts)
        if user_parts is not None
        else len(user_prompt)
    )
    return len(system_prompt) + user_content_chars


def _input_content_char_count(value: object) -> int:
    if isinstance(value, dict) and value.get("type") == "image_url":
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(_input_content_char_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_input_content_char_count(item) for item in value)
    return 0


def resolve_llm_request_body_limit_bytes(
    explicit: int | None = None,
    *,
    file_fallbacks: dict[str, str] | None = None,
) -> int | None:
    value = _resolve_int(
        explicit,
        DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV,
        None,
        default=DEFAULT_DOCTRANSAI_LLM_MAX_REQUEST_BYTES,
        file_fallbacks=file_fallbacks,
    )
    return value if value > 0 else None


def resolve_llm_input_char_limit(
    explicit: int | None = None,
    *,
    file_fallbacks: dict[str, str] | None = None,
) -> int | None:
    value = _resolve_int(
        explicit,
        DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV,
        None,
        default=DEFAULT_DOCTRANSAI_LLM_MAX_INPUT_CHARS,
        file_fallbacks=file_fallbacks,
    )
    return value if value > 0 else None


def _resolve_string(
    explicit: str | None,
    primary_env: str,
    fallback_env: str | None,
    *,
    file_fallbacks: dict[str, str] | None = None,
) -> str | None:
    if explicit is not None:
        return explicit
    modern = {DOCTRANSAI_LLM_API_KEY_ENV: "DATAPROXY_GENERATION_API_KEY",
              DOCTRANSAI_LLM_BASE_URL_ENV: "DATAPROXY_GENERATION_BASE_URL"}.get(primary_env)
    keys = [k for k in (primary_env, modern, fallback_env) if k]
    return next((os.environ[k] for k in keys if os.environ.get(k)), None) or next(
        ((file_fallbacks or {})[k] for k in keys if (file_fallbacks or {}).get(k)), None)


def _resolve_float(
    explicit: float | None,
    primary_env: str,
    fallback_env: str | None,
    *,
    default: float,
    file_fallbacks: dict[str, str] | None = None,
) -> float:
    if explicit is not None:
        return float(explicit)
    value = (
        os.environ.get(primary_env)
        or (os.environ.get(fallback_env) if fallback_env is not None else None)
        or (file_fallbacks or {}).get(primary_env)
        or ((file_fallbacks or {}).get(fallback_env) if fallback_env is not None else None)
    )
    return float(value) if value is not None else default


def _resolve_int(
    explicit: int | None,
    primary_env: str,
    fallback_env: str | None,
    *,
    default: int,
    file_fallbacks: dict[str, str] | None = None,
) -> int:
    if explicit is not None:
        return int(explicit)
    value = (
        os.environ.get(primary_env)
        or (os.environ.get(fallback_env) if fallback_env is not None else None)
        or (file_fallbacks or {}).get(primary_env)
        or ((file_fallbacks or {}).get(fallback_env) if fallback_env is not None else None)
    )
    return int(value) if value is not None else default


def _load_dataproxy_env_fallbacks(explicit_path: Path | None = None) -> dict[str, str]:
    configured = explicit_path or os.environ.get("DOCTRANSAI_ENV_FILE")
    root = os.environ.get(DOCTRANSAI_DATAPROXY_ROOT_ENV)
    if not configured and not root:
        return {}
    env_path = Path(configured).expanduser() if configured else Path(root).expanduser() / ".env"
    if not env_path.exists():
        if configured:
            raise DoctransaiLLMConfigurationError(f"Configured environment file not found: {env_path}")
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ")
        if key.startswith(("DOCTRANSAI_LLM_", "DATAPROXY_GENERATION_", "DATAPROXY_QWEN_")):
            values[key] = value.strip().strip('"').strip("'")
    return values


def _response_text_preview(response: httpx.Response, *, limit: int = 2000) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"
