import json

import httpx
import pytest

from doctransai.llm.client import DoctransaiLLMClient, DoctransaiLLMConfig, DoctransaiLLMResponseError


def sse(events, done=True):
    return ("\n\n".join("data: " + json.dumps(e) for e in events) + ("\n\ndata: [DONE]\n\n" if done else "\n\n")).encode()


def client_for(data):
    return DoctransaiLLMClient(DoctransaiLLMConfig(api_key="test", base_url="https://example.invalid/v1",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=data, headers={"content-type": "text/event-stream"}))))


def test_stream_reassembles_tool_arguments_and_keeps_usage():
    data = sse([
        {"model": "kimi-k3", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call1", "function": {"name": "inspect_", "arguments": "{"}}]}}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"name": "document", "arguments": "}"}}]}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"total_tokens": 20}},
    ])
    response = client_for(data).chat([], [])
    call = response["message"]["tool_calls"][0]
    assert call["function"] == {"name": "inspect_document", "arguments": "{}"}
    assert response["usage"] == {"total_tokens": 20}


@pytest.mark.parametrize("reason,done", [("length", True), (None, True), ("tool_calls", False)])
def test_truncated_stream_is_not_a_tool_response(reason, done):
    data = sse([{"choices": [{"delta": {}, "finish_reason": reason}]}], done=done)
    with pytest.raises(DoctransaiLLMResponseError, match="Incomplete"):
        client_for(data).chat([], [])


def test_missing_usage_is_unknown_not_zero():
    response = client_for(sse([{"choices": [{"delta": {"content": "done"}, "finish_reason": "stop"}]}])).chat([], [])
    assert response["usage"] is None


def test_explicit_generation_config_does_not_replace_project_model(tmp_path, monkeypatch):
    for name in ("DOCTRANSAI_LLM_API_KEY", "DOCTRANSAI_LLM_BASE_URL", "DOCTRANSAI_LLM_MODEL",
                 "DATAPROXY_GENERATION_API_KEY", "DATAPROXY_GENERATION_BASE_URL", "DATAPROXY_QWEN_API_KEY", "DATAPROXY_QWEN_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / "provider.env"
    env.write_text('DATAPROXY_GENERATION_API_KEY="local-test"\nDATAPROXY_GENERATION_BASE_URL="https://example.invalid/v1"\nDATAPROXY_GENERATION_MODEL=other-model\n')
    client = DoctransaiLLMClient(DoctransaiLLMConfig(env_file=env))
    assert client.api_key == "local-test"
    assert client.base_url == "https://example.invalid/v1"
    assert client.model_name == "kimi-k3"
    assert client.temperature == 1.0


def test_explicit_temperature_is_preserved():
    client = DoctransaiLLMClient(DoctransaiLLMConfig(api_key="test", base_url="https://example.invalid/v1", temperature=0.2))
    assert client.temperature == 0.2


def test_explicit_kimi_k3_reasoning_effort_is_sent():
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = DoctransaiLLMClient(DoctransaiLLMConfig(
        api_key="test", base_url="https://example.invalid/v1", reasoning_effort="high",
        transport=httpx.MockTransport(handler)))
    assert client.generate(system_prompt="sys", user_prompt="usr") == "ok"
    assert captured["reasoning_effort"] == "high"


def test_invalid_kimi_k3_reasoning_effort_is_rejected():
    with pytest.raises(ValueError, match="reasoning_effort"):
        DoctransaiLLMClient(DoctransaiLLMConfig(
            api_key="test", base_url="https://example.invalid/v1", reasoning_effort="medium"))


def test_deadline_prevents_request():
    with pytest.raises(TimeoutError):
        client_for(b"").chat([], [], deadline=0)


def test_stream_error_preserves_diagnostic_without_exposing_key():
    with pytest.raises(DoctransaiLLMResponseError) as captured:
        client_for(sse([{"error": {"code": "InternalError", "message": "failure test"}}])).chat([], [])
    assert "InternalError" in str(captured.value)
    assert "<redacted>" in str(captured.value)
    assert captured.value.retryable
