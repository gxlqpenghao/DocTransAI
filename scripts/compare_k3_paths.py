"""Explicit experiment runner. Isolates variants in this process; no product defaults change."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

import httpx
from doctransai.config import RuntimeConfig
import doctransai.conversion as conversion
from doctransai.data_layer.view import SourceView
from doctransai.llm.client import DoctransaiLLMClient, DoctransaiLLMConfig
from doctransai.types import TaskSpec


def text_chars(value):
    if isinstance(value,dict) and value.get('type')=='image_url':return 0
    if isinstance(value,str):return len(value)
    if isinstance(value,list):return sum(text_chars(x) for x in value)
    if isinstance(value,dict):return sum(text_chars(x) for x in value.values())
    return 0


def image_count(value):
    if isinstance(value,dict):
        if value.get('type')=='image_url':return 1
        return sum(image_count(x) for x in value.values())
    if isinstance(value,list):return sum(image_count(x) for x in value)
    return 0


class MeasuredClient(DoctransaiLLMClient):
    def __init__(self, config, log):
        super().__init__(config);self.log=log;self.index=0
        if self.model_name!='kimi-k3':raise ValueError('This experiment is fixed to kimi-k3')
    def chat(self,messages,tools,**kwargs):
        self.index+=1;start=time.monotonic();original=httpx.Response.iter_lines
        row=dict(call=self.index,message_count=len(messages),input_images=image_count(messages),
            text_chars_by_role={role:sum(text_chars(m.get('content')) for m in messages if m['role']==role) for role in ('system','user','assistant','tool')},
            tool_schema_chars=len(json.dumps(tools,ensure_ascii=False)),
            prior_reasoning_chars=sum(len(m.get('reasoning_content','')) for m in messages),
            request_body_bytes=len(json.dumps(dict(messages=messages,tools=tools),ensure_ascii=False).encode()),
            first_event_seconds=None,first_reasoning_seconds=None,first_answer_or_tool_seconds=None)
        def observe(response):
            for line in original(response):
                if line.startswith('data:'):
                    elapsed=time.monotonic()-start
                    if row['first_event_seconds'] is None:row['first_event_seconds']=elapsed
                    try:
                        event=json.loads(line[5:].strip())
                        for choice in event.get('choices',[]):
                            delta=choice.get('delta',{})
                            if delta.get('reasoning_content') and row['first_reasoning_seconds'] is None:row['first_reasoning_seconds']=elapsed
                            if (delta.get('content') or delta.get('tool_calls')) and row['first_answer_or_tool_seconds'] is None:row['first_answer_or_tool_seconds']=elapsed
                    except (ValueError,TypeError):pass
                yield line
        httpx.Response.iter_lines=observe
        try:
            response=super().chat(messages,tools,**kwargs)
            row.update(status='completed',usage=response.get('usage'),model=response.get('model'))
            if response.get('model')!='kimi-k3':raise ValueError('Provider returned a different model')
            return response
        except Exception as exc:
            row.update(status='failed',error_type=type(exc).__name__,usage=None)
            raise
        finally:
            httpx.Response.iter_lines=original
            row['elapsed_seconds']=time.monotonic()-start
            with self.log.open('a') as out:out.write(json.dumps(row,ensure_ascii=False)+'\n')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--task-file',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--profile',choices=['current','continuous','lean','compact','review'],required=True)
    ap.add_argument('--document',type=Path)
    ap.add_argument('--budget',type=float,default=900)
    ap.add_argument('--env-file',type=Path,required=True)
    ap.add_argument('--render-script',type=Path,required=True)
    ap.add_argument('--render-python',required=True)
    args=ap.parse_args()
    if args.profile=='review' and args.document is None:ap.error('--document is required for paired review')
    runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    previous=json.loads(args.task_file.read_text())['task']
    task=TaskSpec(Path(previous['bundle_path']),Path(previous['template_path']),args.output_dir,
        '依据选定源材料填写模板，保留固定文字、格式和图文归属，无依据内容留空。检查输出完整性和可读性。',
        source_file=Path(previous['source_file']),document_id=previous.get('document_id'),source_refs=tuple(previous.get('source_refs',[])))
    config=RuntimeConfig(review_enabled=args.profile=='review',max_seconds=args.budget,model='kimi-k3',env_file=args.env_file,
        render_script=args.render_script,render_python=args.render_python)
    # Restore hooks on exit; they are experimental process-local variants, not product behavior.
    original_initial=SourceView.initial;original_agent=conversion.run_agent
    def lean_initial(source,max_chars):
        view=original_initial(source,min(max_chars,12000))
        if task.source_refs:
            view['evidence']=[];view['evidence_omitted']=view['evidence_total']
            view['selected_native_objects']=[source.read(refs=[ref],max_chars=16000)['objects'][0] for ref in task.source_refs]
        view['catalog']=[{k:r[k] for k in ('ref','kind','title')} for r in view['catalog']]
        view['images']=[{k:r[k] for k in ('ref','asset_type','page_anchor','cell_anchor','caption')} for r in view['images']]
        view['note']='Initial view only. Use read_source for full native objects/search and image context. Omitted text is not missing evidence. All original refs and tools remain available.'
        return view
    def same_history(*a,**kw):
        kw['review_input']=None
        return original_agent(*a,**kw)
    from doctransai.documents.docx import DocxEditor
    from doctransai.documents.xlsx import XlsxEditor
    inspections={cls:cls.inspect for cls in (DocxEditor,XlsxEditor)}
    def compact_inspection(original):
        def inspect(editor,*a,**kw):
            snapshot=original(editor,*a,**kw)
            if kw.get('detail') or kw.get('node_ids'):return snapshot
            if getattr(editor,'format_key','docx')=='xlsx':
                all_nodes=snapshot['nodes']
                snapshot['nodes']=[n for n in all_nodes if n.get('value') is not None or n.get('formula')]
                snapshot['omitted_empty_cells']=len(all_nodes)-len(snapshot['nodes'])
                snapshot['view_note']='Empty cells are omitted from this summary, NOT protected/unavailable. Construct exact addresses within sheets; inspect_document(node_ids=[range]) returns full values and formats on demand.'
            else:
                snapshot['nodes']=[{k:v for k,v in n.items() if k!='text'} if n['kind'] in ('cell','row') else n for n in snapshot['nodes']]
                snapshot['view_note']='Container text is not duplicated. Paragraphs carry text and cell_id; cells carry row_id. All native IDs remain valid.'
            return snapshot
        return inspect
    if args.profile in ('lean','compact'):SourceView.initial=lean_initial
    if args.profile in ('continuous','lean','compact'):conversion.run_agent=same_history
    if args.profile=='compact':
        for cls,original in inspections.items():cls.inspect=compact_inspection(original)
    client=MeasuredClient(DoctransaiLLMConfig(env_file=args.env_file,model_name='kimi-k3',temperature=1.0,max_tokens=5000),args.output_dir/'request-metrics.jsonl')
    try:
        result=conversion.convert(task,config=config,client=client,existing_document=args.document if args.profile=='review' else None,
                                  progress=lambda x:print(x,flush=True))
    finally:
        SourceView.initial=original_initial;conversion.run_agent=original_agent
        for cls,original in inspections.items():cls.inspect=original
    fingerprint=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (args.output_dir/'experiment.json').write_text(json.dumps(dict(profile=args.profile,commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        task_file=str(args.task_file),runner_sha256=runner_sha256,model='kimi-k3',temperature=1.0,max_text_tokens=5000,budget=args.budget,
        source_sha256=fingerprint(task.source_file),template_sha256=fingerprint(task.template_path),bundle_sha256=fingerprint(task.bundle_path),
        prompt_policy='identical production policy',tool_policy='identical production tools and safeguards',
        variant='continuous: unchanged input, no context reset; lean: smaller reversible source view plus no context reset; compact: lean plus on-demand empty/container structure; current: unchanged editing path; review: paired addon only'),ensure_ascii=False,indent=2))
    print(json.dumps(result.__dict__,ensure_ascii=False))


if __name__=='__main__':main()
