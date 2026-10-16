import json
import httpx
import pytest

from doctransai.config import RuntimeConfig
from doctransai.llm.client import DoctransaiLLMClient, DoctransaiLLMConfig


def test_runtime_precedence_and_no_silent_model_lock(tmp_path, monkeypatch):
    f=tmp_path/'backend.env'
    f.write_text('DOCTRANSAI_LLM_MODEL=file-model\nDOCTRANSAI_LLM_MAX_TOKENS=24000\nDOCTRANSAI_LLM_REASONING_EFFORT=medium\nDOCTRANSAI_DOCX_RENDERER=/renderer/render_docx.py\n')
    c=RuntimeConfig.from_environment(env_file=f)
    assert (c.model,c.max_output_tokens,c.reasoning_effort)==('file-model',24000,'medium')
    assert str(c.render_script)=='/renderer/render_docx.py'
    monkeypatch.setenv('DOCTRANSAI_LLM_MODEL','env-model')
    monkeypatch.setenv('DOCTRANSAI_LLM_MAX_TOKENS','18000')
    assert RuntimeConfig.from_environment(env_file=f).model=='env-model'
    c=RuntimeConfig.from_environment(env_file=f,model='cli-model',max_output_tokens=12000,reasoning_effort='omit')
    assert (c.model,c.max_output_tokens,c.reasoning_effort)==('cli-model',12000,'omit')


def test_model_specific_defaults():
    assert RuntimeConfig().reasoning_effort=='high'
    assert RuntimeConfig(model='other-vision-model').reasoning_effort=='omit'
    assert RuntimeConfig.from_environment(model='other-vision-model').reasoning_effort=='omit'
    with pytest.raises(ValueError):RuntimeConfig(model='kimi-k3',reasoning_effort='medium')


def test_explicit_budgets_override_invalid_lower_priority_env(monkeypatch):
    monkeypatch.setenv('DOCTRANSAI_LLM_MAX_TOKENS','invalid')
    monkeypatch.setenv('DOCTRANSAI_LLM_TIMEOUT_SECONDS','invalid')
    monkeypatch.setenv('DOCTRANSAI_LLM_TEMPERATURE','invalid')
    c=RuntimeConfig.from_environment(max_output_tokens=1234,llm_timeout_seconds=10,temperature='omit')
    assert c.max_output_tokens==1234 and c.llm_timeout_seconds==10 and c.temperature=='omit'


@pytest.mark.parametrize('method',['generate','chat'])
@pytest.mark.parametrize('effort',['omit','medium'])
def test_generic_wire_parameters(method,effort,monkeypatch):
    monkeypatch.setenv('DOCTRANSAI_LLM_REASONING_EFFORT','high')
    captured={}
    def handle(req):
        captured.update(json.loads(req.content))
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'ok'}}]})
    c=DoctransaiLLMClient(DoctransaiLLMConfig(api_key='test',base_url='https://example.test/v1',
        model_name='other-vision-model',max_tokens=17000,reasoning_effort=effort,temperature='omit',
        token_parameter='max_completion_tokens',transport=httpx.MockTransport(handle)))
    if method=='generate':c.generate(system_prompt='system',user_prompt='input')
    else:c.chat([],[],stream=False)
    assert captured['model']=='other-vision-model'
    assert captured['max_completion_tokens']==17000 and 'max_tokens' not in captured
    assert 'temperature' not in captured
    if effort=='omit':assert 'reasoning_effort' not in captured
    else:assert captured['reasoning_effort']=='medium'


def test_generic_defaults_omit_provider_optional_fields():
    c=DoctransaiLLMClient(DoctransaiLLMConfig(api_key='test',base_url='https://example.test/v1',model_name='vision-model'))
    assert c.reasoning_effort is None and c.temperature is None


def test_stream_usage_can_be_omitted(monkeypatch):
    monkeypatch.setenv('DOCTRANSAI_LLM_STREAM_USAGE','false')
    def handle(req):
        assert 'stream_options' not in json.loads(req.content)
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=b'data: {"choices":[{"delta":{"content":"done"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
    c=DoctransaiLLMClient(DoctransaiLLMConfig(api_key='test',base_url='https://example.test/v1',transport=httpx.MockTransport(handle)))
    c.chat([],[])


def test_remote_reads_backend_file_and_cli_overrides(tmp_path, monkeypatch):
    from doctransai.upstream.dataproxy import command
    for name in ('DOCTRANSAI_DATAPROXY_API_KEY','DOCTRANSAI_DATAPROXY_BASE_URL','DOCTRANSAI_LLM_MODEL'):
        monkeypatch.delenv(name,raising=False)
    f=tmp_path/'backend.env';f.write_text('DOCTRANSAI_DATAPROXY_API_KEY=private-project-key\nDOCTRANSAI_DATAPROXY_BASE_URL=https://example.test\nDOCTRANSAI_LLM_MODEL=vision-model\nDOCTRANSAI_LLM_MAX_TOKENS=22000\n')
    captured={}
    def run(**kwargs):captured.update(kwargs);return {'status':'completed'}
    monkeypatch.setattr(command,'run_remote',run)
    assert command.main(['--env-file',str(f),'--job-id','job','--template','t.docx','--output-dir','out','--instruction','fill','--model','selected-model'])==0
    assert captured['api_key']=='private-project-key'
    assert captured['base_url']=='https://example.test'
    assert captured['config'].model=='selected-model'
    assert captured['config'].max_output_tokens==22000
    assert captured['config'].reasoning_effort=='omit'

@pytest.mark.parametrize('method',['generate','chat'])
@pytest.mark.parametrize('effort',['on','off'])
@pytest.mark.parametrize('model,url,key',[
    ('qwen3.8-flash','https://dashscope.aliyuncs.com/compatible-mode/v1','enable_thinking'),
    ('deepseek-flash','https://api.deepseek.com/v1','thinking'),
])
def test_thinking_switch_wire(method,effort,model,url,key):
    captured={}
    def handle(req):
        captured.update(json.loads(req.content))
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'ok'}}]})
    c=DoctransaiLLMClient(DoctransaiLLMConfig(api_key='test',base_url=url,model_name=model,
        reasoning_effort=effort,transport=httpx.MockTransport(handle)))
    if method=='generate':c.generate(system_prompt='system',user_prompt='input')
    else:c.chat([],[],stream=False)
    assert 'reasoning_effort' not in captured
    assert captured[key]==({'type':'enabled' if effort=='on' else 'disabled'} if key=='thinking' else effort=='on')


def test_thinking_switch_rejects_unsupported_models_and_gateways():
    with pytest.raises(ValueError):RuntimeConfig(model='kimi-k3',reasoning_effort='off')
    with pytest.raises(ValueError):RuntimeConfig(model='unknown',reasoning_effort='off')
    with pytest.raises(ValueError):
        DoctransaiLLMClient(DoctransaiLLMConfig(api_key='test',base_url='https://unknown.test/v1',
            model_name='qwen3.8-flash',reasoning_effort='off'))
