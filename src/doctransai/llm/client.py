from __future__ import annotations

import json
import os
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

_FALLBACK_API_KEY_ENV = "DATAPROXY_QWEN_API_KEY"
_FALLBACK_BASE_URL_ENV = "DATAPROXY_QWEN_BASE_URL"
_DEFAULT_DATAPROXY_ROOT = Path("/Users/paul/Coding/DataProxy")


class DoctransaiLLMConfigurationError(ValueError):
    pass


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


class DoctransaiLLMClient:
    def __init__(self, config: DoctransaiLLMConfig | None = None) -> None:
        resolved = config or DoctransaiLLMConfig()
        file_fallbacks = _load_dataproxy_env_fallbacks()
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
        self.model_name = resolved.model_name or os.environ.get(DOCTRANSAI_LLM_MODEL_ENV) or DEFAULT_DOCTRANSAI_LLM_MODEL
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
            default=0.0,
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
            default=0.0,
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
    return (
        os.environ.get(primary_env)
        or (os.environ.get(fallback_env) if fallback_env is not None else None)
        or (file_fallbacks or {}).get(primary_env)
        or ((file_fallbacks or {}).get(fallback_env) if fallback_env is not None else None)
    )


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


def _load_dataproxy_env_fallbacks() -> dict[str, str]:
    dataproxy_root = Path(
        os.environ.get(DOCTRANSAI_DATAPROXY_ROOT_ENV)
        or _DEFAULT_DATAPROXY_ROOT
    ).expanduser()
    env_path = dataproxy_root / ".env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _response_text_preview(response: httpx.Response, *, limit: int = 2000) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"
