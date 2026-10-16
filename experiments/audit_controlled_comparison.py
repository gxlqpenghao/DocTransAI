"""Three-arm audit-only comparison. Never edits source runs or production settings."""
import argparse,copy,hashlib,json,time
from pathlib import Path
from doctransai.audit import ledger,POLICY,AUDIT_TOOL,validate_assessments,save_audit,delivery_audit
from doctransai.config import RuntimeConfig
from doctransai.data_layer.artifact import read_source_input
from doctransai.data_layer.view import SourceView
from doctransai.documents.preview import image_part
from doctransai.llm.client import DoctransaiLLMClient,DoctransaiLLMConfig


def main():
 p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--env-file',type=Path,required=True);p.add_argument('--fast-model',default='qwen3.8-flash');a=p.parse_args()
 if a.output.exists():raise ValueError('Use a new output directory')
 a.output.mkdir(parents=True);report=json.loads((a.run_dir/'review.json').read_text());base=ledger(a.run_dir)
 source=SourceView(read_source_input(Path(report['task']['bundle_path']),a.run_dir),document_id=report['task'].get('document_id'),source_file=Path(report['task']['source_file']) if report['task'].get('source_file') else None)
 payload={k:base[k] for k in ('fields','operations','instruction')};payload['source_context']={k:v for k,v in base['source_context'].items() if k not in {'parse_quality','warnings','diagnostics','quality'}}
 pages=report.get('output_pages',[])[:8];payload['visual_coverage']={'total_pages':len(report.get('output_pages',[])),'supplied_pages':len(pages)}
 images=[]
 for i,page in enumerate(pages,1):images.extend([{'type':'text','text':f'Final document page {i}'},image_part(Path(page))])
 doc=Path(report['output_path']);original_hash=hashlib.sha256(doc.read_bytes()).hexdigest();assert original_hash==base['document_sha256']
 plan={'document_sha256':original_hash,'source_run':str(a.run_dir),'order':['baseline','compact','fast'], 'max_output_tokens':16000,'temperature':1.0,'output_page_count':len(pages),'candidate_count':len(base['fields']),'model_calls_per_arm':1,'retries':0}
 (a.output/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
 summaries=[]
 for name,model,effort in [('baseline','kimi-k3','high'),('compact','kimi-k3','high'),('fast',a.fast_model,'on')]:
  dest=a.output/name;dest.mkdir();data=copy.deepcopy(payload);policy=POLICY
  if name=='compact':
   for f in data['fields']:
    for k in ('field_label','category','reason','review_action','evidence'):f.pop(k,None)
   for k in ('note','prepared_asset_refs','prepared_asset_count','prepared_asset_note','prepared_source_page_count'):data['source_context'].pop(k,None)
   policy+='\n输出应简明完整：reason和review_action各用一个短句，避免重复复述原值/最终值和通用免责声明；低确信度或未填入仍需指出具体疑点及核对动作。not_field只需简短标明固定标签或版式。不得为缩短输出省略候选、关键理由或必要证据。'
  text=json.dumps(data,ensure_ascii=False,default=str,**({'separators':(',',':')} if name=='compact' else {}))
  messages=[{'role':'system','content':policy},{'role':'user','content':[{'type':'text','text':text},*images]}]
  wire=json.dumps({'messages':messages,'tools':[AUDIT_TOOL]},ensure_ascii=False)
  (dest/'request.json').write_text(wire)
  cfg=RuntimeConfig.from_environment(env_file=a.env_file,model=model,reasoning_effort=effort,temperature=1.0,max_output_tokens=16000,llm_timeout_seconds=180,max_seconds=600)
  client=DoctransaiLLMClient(DoctransaiLLMConfig(env_file=cfg.env_file,model_name=model,reasoning_effort=effort,temperature=1.0,max_tokens=16000,timeout_seconds=180,token_parameter=cfg.token_parameter))
  events=[];client.progress=lambda msg:events.append({'seconds':round(time.monotonic()-start,3),'message':msg})
  audit=copy.deepcopy(base);audit['visual_coverage']=data['visual_coverage'];start=time.monotonic()
  info={'arm':name,'model':model,'effort':effort,'request_sha256':hashlib.sha256(wire.encode()).hexdigest(),'input_text_chars':len(text),'system_chars':len(policy)}
  print('START',name,model,flush=True)
  try:
   response=client.chat(messages,[AUDIT_TOOL],stream=True,deadline=start+600)
   info['seconds']=round(time.monotonic()-start,3);info['usage']=response.get('usage');info['returned_model']=response.get('model')
   calls=response.get('message',{}).get('tool_calls',[])
   if len(calls)!=1 or calls[0]['function']['name']!='submit_audit':raise ValueError('Expected one complete audit')
   raw=calls[0]['function']['arguments'];assess=json.loads(raw) if isinstance(raw,str) else raw
   (dest/'assessments.json').write_text(json.dumps(assess,ensure_ascii=False,indent=2))
   validate_assessments(audit,assess['assessments'],source);audit.update(status='assessed',model=model,reasoning_effort=effort,assessment_seconds=info['seconds']);save_audit(dest,audit)
   info.update(status='assessed',counts=delivery_audit(audit)['counts'])
  except Exception as exc:
   info.update(status='failed',seconds=round(time.monotonic()-start,3),error_type=type(exc).__name__,error=str(exc).replace(client.api_key,'<redacted>')[:500])
  (dest/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2));(dest/'summary.json').write_text(json.dumps(info,ensure_ascii=False,indent=2));summaries.append(info);(a.output/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2));print('RESULT',json.dumps(info,ensure_ascii=False),flush=True)
  assert hashlib.sha256(doc.read_bytes()).hexdigest()==original_hash
if __name__=='__main__':main()
