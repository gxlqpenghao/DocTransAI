import base64
import hashlib
import json

import httpx
import pytest

from doctransai.config import RuntimeConfig
from doctransai.llm.client import DoctransaiLLMClient, DoctransaiLLMConfig
from doctransai.llm.diagnostics import ModelDiagnostics
from doctransai.documents.preview import IMAGE_CONTENT_REGISTRY


def sse(events, done=True):
    return ("\n\n".join("data: " + json.dumps(e) for e in events) + ("\n\ndata: [DONE]\n\n" if done else "\n\n")).encode()


def captured_transport(captured):
    def handler(request):
        captured.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, content=b"", status_code=500)
    return httpx.MockTransport(handler)


def make_client(tmp_path, captured=None, secret="secret-key-123", stream_bytes=None):
    if stream_bytes is None:
        tool_call_delta = {"index": 0, "id": "call1",
                           "function": {"name": "finish", "arguments": "{\"summary\":\"done\"}"}}
        stream_bytes = sse([
            {"model": "kimi-k3", "choices": [{"index": 0, "delta": {"reasoning_content": "thinking hard"}}]},
            {"model": "kimi-k3", "choices": [{"index": 0, "delta": {"content": "Hello"}}]},
            {"model": "kimi-k3", "choices": [{"index": 0, "delta": {"tool_calls": [tool_call_delta]}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
            {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                                      "prompt_tokens_details": {"cached_tokens": 2},
                                      "completion_tokens_details": {"reasoning_tokens": 3}}},
        ])

    def handler(request):
        if captured is not None:
            captured.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, content=stream_bytes, headers={"content-type": "text/event-stream"})

    recorder = ModelDiagnostics(tmp_path, redact_secrets=[secret])
    client = DoctransaiLLMClient(DoctransaiLLMConfig(
        api_key=secret, base_url="https://example.invalid/v1",
        transport=httpx.MockTransport(handler), diagnostics=recorder))
    return client, recorder


def read_records(tmp_path):
    return [json.loads(line) for line in (tmp_path / "model-diagnostics.jsonl").read_text().splitlines()]


def test_diagnostics_switch_defaults_off_and_env_enables(tmp_path, monkeypatch):
    assert RuntimeConfig.from_environment().model_diagnostics is False
    monkeypatch.setenv("DOCTRANSAI_MODEL_DIAGNOSTICS", "1")
    assert RuntimeConfig.from_environment().model_diagnostics is True
    monkeypatch.setenv("DOCTRANSAI_MODEL_DIAGNOSTICS", "false")
    assert RuntimeConfig.from_environment().model_diagnostics is False
    # A disabled client never creates diagnostics artefacts.
    client = DoctransaiLLMClient(DoctransaiLLMConfig(
        api_key="test", base_url="https://example.invalid/v1",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=sse(
            [{"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}])))))
    assert client.diagnostics is None


def test_recording_does_not_change_request_content(tmp_path):
    captured_on, captured_off = [], []

    def silent_handler(captured):
        def handler(request):
            captured.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, content=sse([{"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}]))
        return httpx.MockTransport(handler)

    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
    tools = [{"type": "function", "function": {"name": "finish", "parameters": {}}}]
    on_client, _ = make_client(tmp_path, captured=captured_on)
    off_client = DoctransaiLLMClient(DoctransaiLLMConfig(
        api_key="test", base_url="https://example.invalid/v1", transport=silent_handler(captured_off)))
    on_client.chat(messages, tools)
    off_client.chat(messages, tools)
    assert captured_on == captured_off  # identical payload, byte-for-byte via json equality


def test_success_records_reasoning_content_snapshots_and_usage(tmp_path):
    tiny_png = base64.b64encode(b"not-a-real-image-but-stable-bytes").decode()
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "before image"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + tiny_png}},
        {"type": "text", "text": "after image"},
    ]}]
    client, recorder = make_client(tmp_path)
    response = client.chat(messages, [{"type": "function", "function": {"name": "finish"}}])
    assert response["_diagnostics_request_id"] == "req-0001"

    records = read_records(tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "ok" and record["incomplete"] is False
    assert record["response"]["reasoning_content"] == "thinking hard"
    assert record["response"]["content"] == "Hello"
    assert record["response"]["tool_calls"][0]["function"]["name"] == "finish"
    assert record["stream_first_event_times"]["reasoning"] is not None
    assert record["stream_first_event_times"]["content"] is not None
    assert record["stream_first_event_times"]["tool_args"] is not None
    # Unknown tokens stay null, known tokens stay exact.
    assert record["usage_normalized"] == {"input_tokens": 10, "output_tokens": 5,
                                          "reasoning_tokens": 3, "cached_tokens": 2, "image_tokens": None}

    snapshot = json.loads((tmp_path / "request-snapshots" / "req-0001-input.json").read_text())
    parts = snapshot["messages"][0]["content"]
    assert parts[0]["text"] == "before image" and parts[2]["text"] == "after image"  # order preserved
    image_ref = parts[1]
    assert image_ref["type"] == "image_url_redacted"
    assert "base64" not in json.dumps(snapshot) or image_ref["sha256"]
    assert image_ref["sha256"] == hashlib.sha256(base64.b64decode(tiny_png)).hexdigest()
    assert (tmp_path / "images-manifest.json").exists()


def test_failure_retains_partial_fragments_and_marks_incomplete(tmp_path):
    first_chunk = sse([{"model": "kimi-k3", "choices": [{"index": 0, "delta": {"reasoning_content": "partial thought"}}]}],
                      done=False)

    def flaky_stream():
        yield first_chunk
        raise httpx.ReadError("connection dropped mid-stream")

    def broken_handler(request):
        return httpx.Response(200, content=flaky_stream(), headers={"content-type": "text/event-stream"})

    client, recorder = make_client(tmp_path, stream_bytes=b"")  # recorder only; transport replaced below
    client.transport = httpx.MockTransport(broken_handler)
    with pytest.raises(httpx.ReadError):
        client.chat([{"role": "user", "content": "hello"}], [])

    records = read_records(tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "error" and record["incomplete"] is True
    assert record["error"]["error_type"] == "ReadError"
    assert record["response"]["reasoning_content"] == "partial thought"  # fragments retained
    assert record["stream_first_event_times"]["reasoning"] is not None
    assert record["snapshot_file"] == "req-0001-input.json"  # input kept even though request failed
    assert (tmp_path / "request-snapshots" / "req-0001-input.json").exists()


def test_credentials_never_appear_in_diagnostics(tmp_path):
    secret = "super-secret-api-key-xyz"
    failing = sse([{"error": {"code": "Throttling", "message": "quota exceeded key " + secret}}], done=False)
    client, _ = make_client(tmp_path, secret=secret, stream_bytes=failing)
    with pytest.raises(Exception):
        client.chat([{"role": "user", "content": "hello"}], [])

    directory = tmp_path
    for path in directory.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert secret not in text, f"credential leaked into {path}"
            assert "Authorization" not in text


def test_default_high_is_sent_without_automatic_escalation(tmp_path, monkeypatch):
    monkeypatch.delenv('DOCTRANSAI_LLM_REASONING_EFFORT', raising=False)
    monkeypatch.delenv('DOCTRANSAI_ENV_FILE', raising=False)
    from doctransai.config import RuntimeConfig
    assert RuntimeConfig().reasoning_effort == 'high'
    assert RuntimeConfig.from_environment().reasoning_effort == 'high'
    assert RuntimeConfig.from_environment(reasoning_effort='max').reasoning_effort == 'max'
    captured=[]
    client, recorder = make_client(tmp_path, captured=captured)
    client.chat([{'role':'user','content':'fill'}], [])
    client.chat([{'role':'user','content':'check'}], [])
    assert [p['reasoning_effort'] for p in captured] == ['high', 'high']
