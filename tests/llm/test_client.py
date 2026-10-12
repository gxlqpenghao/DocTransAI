from __future__ import annotations

import json

import httpx
import pytest

from doctransai.llm import (
    DEFAULT_DOCTRANSAI_LLM_MODEL,
    DOCTRANSAI_LLM_API_KEY_ENV,
    DOCTRANSAI_LLM_BASE_URL_ENV,
    DOCTRANSAI_DATAPROXY_ROOT_ENV,
    DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV,
    DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV,
    DoctransaiLLMClient,
    DoctransaiLLMConfig,
    DoctransaiLLMConfigurationError,
    DoctransaiLLMHTTPStatusError,
    DoctransaiLLMInputTooLargeError,
    DoctransaiLLMRequestTooLargeError,
    generate_text_with_doctransai_llm,
)


def test_doctransai_llm_client_uses_project_model_and_env_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        payload = json.loads(request.content.decode("utf-8"))
        captured["payload"] = payload
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"decisions":[]}',
                        }
                    }
                ]
            },
        )

    monkeypatch.setenv(DOCTRANSAI_LLM_API_KEY_ENV, "api-key")
    monkeypatch.setenv(DOCTRANSAI_LLM_BASE_URL_ENV, "https://llm.example.com/v1")

    text = generate_text_with_doctransai_llm(
        system_prompt="system prompt",
        user_prompt="user prompt",
        config=DoctransaiLLMConfig(transport=httpx.MockTransport(handler)),
    )

    assert text == '{"decisions":[]}'
    assert captured["url"] == "https://llm.example.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer api-key"
    assert captured["payload"]["model"] == DEFAULT_DOCTRANSAI_LLM_MODEL
    assert captured["payload"]["messages"][0]["content"] == "system prompt"
    assert captured["payload"]["messages"][1]["content"] == "user prompt"


def test_doctransai_llm_client_uses_explicit_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_API_KEY_ENV, "api-key")
    monkeypatch.setenv(DOCTRANSAI_LLM_BASE_URL_ENV, "https://llm.example.com/v1")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "custom-model"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = DoctransaiLLMClient(
        DoctransaiLLMConfig(
            model_name="custom-model",
            transport=httpx.MockTransport(handler),
        )
    )

    assert client.generate(system_prompt="sys", user_prompt="usr") == "ok"


def test_doctransai_llm_client_sends_multimodal_user_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        captured["payload"] = payload
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setenv(DOCTRANSAI_LLM_API_KEY_ENV, "api-key")
    monkeypatch.setenv(DOCTRANSAI_LLM_BASE_URL_ENV, "https://llm.example.com/v1")

    client = DoctransaiLLMClient(
        DoctransaiLLMConfig(
            transport=httpx.MockTransport(handler),
        )
    )

    client.generate(
        system_prompt="sys",
        user_prompt="usr",
        user_parts=[
            {"type": "text", "text": "usr"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA", "detail": "high"}},
        ],
    )

    assert isinstance(captured["payload"]["messages"][1]["content"], list)
    assert captured["payload"]["messages"][1]["content"][1]["type"] == "image_url"


def test_doctransai_llm_client_requires_api_key_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DOCTRANSAI_LLM_API_KEY_ENV, raising=False)
    monkeypatch.delenv(DOCTRANSAI_LLM_BASE_URL_ENV, raising=False)
    monkeypatch.delenv("DATAPROXY_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DATAPROXY_QWEN_BASE_URL", raising=False)
    monkeypatch.setenv(DOCTRANSAI_DATAPROXY_ROOT_ENV, "/tmp/doctransai-empty-dataproxy-root")

    with pytest.raises(DoctransaiLLMConfigurationError):
        DoctransaiLLMClient()


def test_doctransai_llm_client_surfaces_http_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "context length exceeded"}},
            request=request,
        )

    monkeypatch.setenv(DOCTRANSAI_LLM_API_KEY_ENV, "api-key")
    monkeypatch.setenv(DOCTRANSAI_LLM_BASE_URL_ENV, "https://llm.example.com/v1")

    client = DoctransaiLLMClient(DoctransaiLLMConfig(transport=httpx.MockTransport(handler)))

    with pytest.raises(DoctransaiLLMHTTPStatusError) as exc_info:
        client.generate(system_prompt="sys", user_prompt="usr")

    message = str(exc_info.value)
    assert "400" in message
    assert "context length exceeded" in message
    assert exc_info.value.status_code == 400


def test_doctransai_llm_client_rejects_oversized_request_before_http(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"http": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["http"] = True
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setenv(DOCTRANSAI_LLM_API_KEY_ENV, "api-key")
    monkeypatch.setenv(DOCTRANSAI_LLM_BASE_URL_ENV, "https://llm.example.com/v1")
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "128")

    client = DoctransaiLLMClient(DoctransaiLLMConfig(transport=httpx.MockTransport(handler)))

    with pytest.raises(DoctransaiLLMRequestTooLargeError) as exc_info:
        client.generate(system_prompt="sys", user_prompt="x" * 1000)

    assert called["http"] is False
    assert exc_info.value.estimated_request_bytes > exc_info.value.max_request_body_bytes
    assert "exceeds configured maximum" in str(exc_info.value)


def test_doctransai_llm_client_rejects_oversized_input_before_http(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"http": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["http"] = True
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setenv(DOCTRANSAI_LLM_API_KEY_ENV, "api-key")
    monkeypatch.setenv(DOCTRANSAI_LLM_BASE_URL_ENV, "https://llm.example.com/v1")
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "1000000")
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, "128")

    client = DoctransaiLLMClient(DoctransaiLLMConfig(transport=httpx.MockTransport(handler)))

    with pytest.raises(DoctransaiLLMInputTooLargeError) as exc_info:
        client.generate(system_prompt="sys", user_prompt="x" * 1000)

    assert called["http"] is False
    assert exc_info.value.estimated_input_chars > exc_info.value.max_input_chars
    assert "exceeds configured maximum" in str(exc_info.value)


def test_doctransai_llm_client_does_not_apply_default_input_char_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"http": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["http"] = True
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setenv(DOCTRANSAI_LLM_API_KEY_ENV, "api-key")
    monkeypatch.setenv(DOCTRANSAI_LLM_BASE_URL_ENV, "https://llm.example.com/v1")
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "1000000")
    monkeypatch.delenv(DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, raising=False)

    client = DoctransaiLLMClient(DoctransaiLLMConfig(transport=httpx.MockTransport(handler)))

    assert client.max_input_chars is None
    assert client.generate(system_prompt="sys", user_prompt="x" * 300_000) == "ok"
    assert called["http"] is True


def test_doctransai_llm_client_reads_dataproxy_env_file_as_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    dataproxy_root = tmp_path / "DataProxy"
    dataproxy_root.mkdir()
    (dataproxy_root / ".env").write_text(
        "\n".join(
            [
                "DATAPROXY_QWEN_API_KEY=file-key",
                "DATAPROXY_QWEN_BASE_URL=https://fallback.example.com/v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv(DOCTRANSAI_LLM_API_KEY_ENV, raising=False)
    monkeypatch.delenv(DOCTRANSAI_LLM_BASE_URL_ENV, raising=False)
    monkeypatch.delenv("DATAPROXY_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DATAPROXY_QWEN_BASE_URL", raising=False)
    monkeypatch.setenv(DOCTRANSAI_DATAPROXY_ROOT_ENV, str(dataproxy_root))

    client = DoctransaiLLMClient(
        DoctransaiLLMConfig(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
            )
        )
    )

    assert client.api_key == "file-key"
    assert client.base_url == "https://fallback.example.com/v1"
    assert client.model_name == DEFAULT_DOCTRANSAI_LLM_MODEL
    assert client.max_tokens == 8192


def test_default_doctransai_model_tracks_kimi_k3() -> None:
    assert DEFAULT_DOCTRANSAI_LLM_MODEL == "kimi-k3"


def test_doctransai_llm_client_default_timeout_supports_long_agent_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_API_KEY_ENV, "api-key")
    monkeypatch.setenv(DOCTRANSAI_LLM_BASE_URL_ENV, "https://llm.example.com/v1")

    client = DoctransaiLLMClient(
        DoctransaiLLMConfig(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
            )
        )
    )

    assert client.timeout_seconds >= 180.0


def test_doctransai_llm_client_default_max_tokens_supports_multi_slot_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_API_KEY_ENV, "api-key")
    monkeypatch.setenv(DOCTRANSAI_LLM_BASE_URL_ENV, "https://llm.example.com/v1")

    client = DoctransaiLLMClient(
        DoctransaiLLMConfig(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
            )
        )
    )

    assert client.max_tokens >= 8192
