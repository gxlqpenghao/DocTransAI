"""Read/edit/render probe. Use a disposable directory; never production templates."""
import argparse, hashlib,json,os,subprocess,time
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--binary',required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();log=[]
 env=dict(os.environ,OFFICECLI_SKIP_UPDATE='1')
 def run(label,*args,timeout=60):
  t=time.monotonic()
  try:r=subprocess.run([a.binary,*map(str,args)],env=env,capture_output=True,text=True,timeout=timeout);code=r.returncode;stdout=r.stdout;stderr=r.stderr
  except subprocess.TimeoutExpired as e:code=-1;stdout='';stderr='timeout'
  row=dict(label=label,seconds=round(time.monotonic()-t,3),exit_code=code);log.append(row)
  (root/(label+'.stdout')).write_text(stdout);(root/(label+'.stderr')).write_text(stderr);(root/'probe.json').write_text(json.dumps(log,indent=2));print(row,flush=True)
 for name in ('fixture.docx','fixture.xlsx','business-template.docx','business-template.xlsx'):
  if not (root/name).exists():continue
  run('read-'+name,'view',root/name,'text','--json')
  run('validate-'+name,'validate',root/name,'--json')
 for ext in ('docx','xlsx'):
  run('merge-'+ext,'merge',root/('fixture.'+ext),root/('merged.'+ext),'--data',root/'data.json','--json')
  run('validate-merged-'+ext,'validate',root/('merged.'+ext),'--json')
 for name in ('merged.docx','merged.xlsx','business-template.docx','business-template.xlsx'):
  if not (root/name).exists():continue
  run('html-'+name,'view',root/name,'html','-o',root/(name+'.html'))
  run('screenshot-'+name,'view',root/name,'screenshot','--render','html','-o',root/(name+'.png'),timeout=60)
if __name__=='__main__':main()
