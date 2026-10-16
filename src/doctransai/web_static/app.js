'use strict';
const $ = id => document.getElementById(id);
const terminal = new Set(['completed','failed','interrupted']);
const phaseIndex = {queued:0,parsing:0,reading:0,converting:1,auditing:2,publishing:3,completed:4};
const statusLabels = {queued:'准备中',running:'运行中',completed:'已完成',failed:'需要检查',interrupted:'已中断'};
let configuration=null,currentJob=null,pollTimer=null,busy=false,viewGeneration=0,historical=false;

async function api(path,options){const r=await fetch(path,options);const body=await r.json();if(!r.ok)throw new Error(body.error||`请求失败（${r.status}）`);return body;}
function openDialog(id){if(!$(id).open)$(id).showModal();}
function panel(name){document.body.dataset.panel=name;document.querySelectorAll('[data-panel]').forEach(b=>{if(b.tagName==='BUTTON')b.setAttribute('aria-pressed',String(b.dataset.panel===name));});}
function error(message){$('form-error').textContent=message;$('form-error').title=message;$('form-error').hidden=!message;if(message){$('detail-message').textContent=message;$('open-details').disabled=false;}}
function updateStart(){
  $('start').disabled=busy||!configuration?.ready;
  $('start').firstElementChild.textContent=busy?'任务运行中':'开始转换';
  for(const kind of ['source','template']){$(kind).disabled=busy;$(kind+'-drop').classList.toggle('locked',busy);}
  document.querySelectorAll('#inline-settings input,#inline-settings select').forEach(el=>el.disabled=busy);
  updateThinking();
}
function settingsSummary(){updateThinking();}
function updateThinking(){
  const model=$('model').value.trim(), supported=Boolean(configuration?.thinking_models?.[model]), kimi=model.split('/').pop()==='kimi-k3';
  const reason=kimi?'当前Kimi K3仅支持思考，无法关闭。':'当前模型与后端服务的思考开关尚未适配。';
  $('thinking-on').disabled=busy||(!supported&&!kimi);$('thinking-off').disabled=busy||!supported;
  const off=$('reasoning-effort').value==='off';
  $('thinking-on').setAttribute('aria-pressed',String(!off&&(supported||kimi)));$('thinking-off').setAttribute('aria-pressed',String(off));
  const onTip='开启：侧重复杂理解、字段对应与核对，通常耗时更长；不保证结果无误。';
  const offTip='关闭：通常响应更快，复杂任务可能遗漏细节；尚未完成本项目的开关质量对照。';
  $('thinking-on-tip').title=(!supported&&!kimi?reason+' ':'')+onTip;
  $('thinking-off-tip').title=(supported?'':reason+' ')+offTip;
  $('thinking-on').setAttribute('aria-label','开启思考');$('thinking-off').setAttribute('aria-label','关闭思考');
  $('thinking-on-tip').dataset.tip=$('thinking-on-tip').title;$('thinking-off-tip').dataset.tip=$('thinking-off-tip').title;
  $('thinking-note').textContent=kimi?'K3 · '+$('reasoning-effort').value+'，不支持关闭':supported?(off?'已关闭思考':'已开启思考'):'沿用后端策略 · 开关未适配';
}
async function loadConfiguration(initial=false){
  try{
    configuration=await api('/api/config');$('version').textContent=`v${configuration.version}`;
    $('config-status').replaceChildren(...configuration.checks.map(check=>{const span=document.createElement('span');span.className=`check ${check.ok?'good':'bad'}`;span.textContent=check.label+(check.ok?'已配置':'未就绪');return span;}));
    document.querySelector('.environment').classList.toggle('warn',!configuration.ready);
    if(initial){$('model').value=configuration.defaults.model;$('max-output-tokens').value=configuration.defaults.max_output_tokens;$('reasoning-effort').value=configuration.defaults.reasoning_effort||'auto';if(configuration.thinking_models?.[$('model').value]&&$('reasoning-effort').value!=='off')$('reasoning-effort').value='on';}
    settingsSummary();updateStart();
  }catch(e){configuration=null;updateStart();$('config-status').textContent='本地服务连接中断';error(e.message);}
}
function clearResult(){
  clearTimeout(pollTimer);viewGeneration++;currentJob=null;historical=false;sessionStorage.removeItem('doctransai.currentJob');
  $('empty-state').hidden=false;$('job-state').hidden=true;$('state-badge').textContent='等待开始';$('state-badge').className='state-badge';
  $('result-heading').textContent='运行结果';$('open-details').disabled=true;
  $('audit-frame').removeAttribute('src');if($('audit-dialog').open)$('audit-dialog').close();
  $('detail-message').textContent='';$('task-ids').textContent='';$('events').replaceChildren();$('extra-downloads').replaceChildren();
}
function fileChanged(kind){
  const file=$(kind).files[0];$(kind+'-drop').classList.toggle('selected',Boolean(file));
  const size=file&&(file.size<1024**2?`${Math.max(1,Math.ceil(file.size/1024))} KiB`:`${(file.size/1024**2).toFixed(2)} MiB`);
  $(kind+'-info').textContent=file?`${file.name} · ${size}`:'点击选择或拖入文件';$(kind+'-info').title=file?.name||'';
  error('');if(!busy)clearResult();
}
for(const kind of ['source','template']){
  $(kind).addEventListener('change',()=>fileChanged(kind));const area=$(kind+'-drop');
  area.addEventListener('dragover',e=>{e.preventDefault();if(!busy)area.classList.add('dragging');});
  area.addEventListener('dragleave',()=>area.classList.remove('dragging'));
  area.addEventListener('drop',e=>{e.preventDefault();area.classList.remove('dragging');if(busy)return;if(e.dataTransfer.files.length===1){$(kind).files=e.dataTransfer.files;fileChanged(kind);}else error('每个位置请选择一份文件。');});
}
for(const button of document.querySelectorAll('[data-open]'))button.addEventListener('click',()=>openDialog(button.dataset.open));
for(const button of document.querySelectorAll('[data-close]'))button.addEventListener('click',()=>button.closest('dialog').close());
for(const button of document.querySelectorAll('.mobile-tabs button'))button.addEventListener('click',()=>panel(button.dataset.panel));
$('model').addEventListener('input',()=>{$('reasoning-effort').value=configuration?.thinking_models?.[$('model').value.trim()]?'on':$('model').value.trim().split('/').pop()==='kimi-k3'?'high':'auto';settingsSummary();});
$('mode').addEventListener('change',settingsSummary);
$('thinking-on').addEventListener('click',()=>{$('reasoning-effort').value=$('model').value.split('/').pop()==='kimi-k3'?'high':'on';updateThinking();});
$('thinking-off').addEventListener('click',()=>{$('reasoning-effort').value='off';updateThinking();});
$('refresh-config').addEventListener('click',()=>loadConfiguration());
$('open-details').addEventListener('click',()=>openDialog('details-dialog'));
$('open-history').addEventListener('click',()=>{loadHistory(false);openDialog('history-dialog');});

function downloadLink(file,label,primary=false){const link=document.createElement('a');link.href=file.url;link.download=file.name;link.textContent=label;if(primary)link.className='main-download';return link;}
function renderJob(job){
  currentJob=job;busy=!terminal.has(job.status);sessionStorage.setItem('doctransai.currentJob',job.id);updateStart();
  $('empty-state').hidden=true;$('job-state').hidden=false;$('open-details').disabled=false;
  $('result-heading').textContent=historical?'历史任务结果':'运行结果';$('state-badge').textContent=statusLabels[job.status]||job.status;$('state-badge').className='state-badge '+job.status;
  $('task-files').textContent=`${job.source} → ${job.template}`;$('task-files').title=$('task-files').textContent;
  const failed=['failed','interrupted'].includes(job.status),index=phaseIndex[job.phase]??0;
  $('status-icon').textContent=job.status==='completed'?'✓':failed?'!':'↻';$('status-icon').className='status-icon'+(failed?' failed':'');
  $('job-message').textContent=job.message;$('job-message').classList.toggle('failed',failed);$('job-message').title=job.message;
  const elapsed=Math.max(0,Math.round(((terminal.has(job.status)?job.updated_at:Date.now()/1000)||Date.now()/1000)-job.created_at));
  $('job-time').textContent=`${job.mode==='workspace'?'工作区':'ZIP'} · ${Math.floor(elapsed/60)}分${elapsed%60}秒`;
  $('phase-track').hidden=terminal.has(job.status);
  document.querySelectorAll('[data-step]').forEach((node,i)=>{node.classList.toggle('done',i<index);node.classList.toggle('active',i===Math.min(index,3));});
  const warnings=job.parse_quality==='degraded'||job.warnings?.length;
  $('quality-warning').hidden=!warnings;$('quality-warning').textContent='解析包含质量警告，请在审计中核对。';
  const audit=job.audit||{},counts=audit.counts||{};
  $('audit-summary').hidden=!audit.status;
  $('audit-summary').textContent=audit.status==='assessed'?`高确信度 ${counts.filled_high||0} · 低确信度 ${counts.filled_low||0} · 未填写 ${counts.unfilled||0}`:'审计尚未完成，已有文档需要人工复核';
  const actions=$('result-actions'),extras=$('extra-downloads');actions.replaceChildren();extras.replaceChildren();
  for(const file of job.files||[]){
    if(file.name==='audit.html'){
      const button=document.createElement('button');button.type='button';button.textContent='查看审计';
      button.addEventListener('click',()=>{$('audit-frame').src=file.url;openDialog('audit-dialog');});actions.append(button);
    }else if(file.name.startsWith('result.')){
      actions.append(downloadLink(file,job.status==='completed'?'下载文档':'下载文档（待复核）',true));
    }else{
      const labels={'audit.json':'审计JSON','review.json':'诊断报告','integration.json':'任务记录','workspace-export.zip':'工作区导出包'};
      extras.append(downloadLink(file,labels[file.name]||file.name));
    }
  }
  $('detail-message').textContent=job.message+(warnings?`\n解析质量：${job.parse_quality||'待确认'}；${job.warnings?.length||0}条警告。`:'');
  $('task-ids').textContent=`本地任务：${job.id}\n解析任务：${job.job_id||'等待创建'}\n工作区：${job.workspace_id||'未创建'}`;
  $('events').replaceChildren(...(job.events||[]).map(event=>{const li=document.createElement('li');li.textContent=`${new Date(event.at*1000).toLocaleTimeString()} · ${event.message}`;return li;}));
}
async function poll(jobId,generation=viewGeneration){
  clearTimeout(pollTimer);
  try{
    const job=await api('/api/jobs/'+jobId);if(generation!==viewGeneration)return;renderJob(job);
    if(!terminal.has(job.status))pollTimer=setTimeout(()=>poll(jobId,generation),2000);else await loadHistory(false);
  }catch(e){
    if(generation!==viewGeneration)return;
    $('job-message').textContent='进度连接中断，正在重连…';pollTimer=setTimeout(()=>poll(jobId,generation),5000);
  }
}
async function loadHistory(restore=true){
  try{
    const {jobs}=await api('/api/jobs');$('history-count').textContent=jobs.length;
    const buttons=jobs.map(job=>{
      const button=document.createElement('button');button.type='button';button.textContent=`${statusLabels[job.status]||job.status} · ${job.source}`;button.disabled=busy&&currentJob?.id!==job.id;
      button.addEventListener('click',()=>{clearTimeout(pollTimer);viewGeneration++;historical=terminal.has(job.status);$('history-dialog').close();panel('result');poll(job.id);});return button;
    });
    $('history-list').replaceChildren(...buttons);
    if(!jobs.length)$('history-list').textContent='暂无任务记录。';
    if(restore){const target=jobs.find(j=>!terminal.has(j.status))||jobs.find(j=>j.id===sessionStorage.getItem('doctransai.currentJob'));if(target)poll(target.id);}
  }catch(e){error('无法读取历史任务：'+e.message);}
}
$('conversion-form').addEventListener('submit',async e=>{
  e.preventDefault();if(busy||!configuration?.ready)return;
  const source=$('source').files[0],template=$('template').files[0];
  if(!source||!template)return error('请选择源文档和目标模板。');
  if(!/\.(docx|xlsx)$/i.test(template.name))return error('模板仅支持DOCX或XLSX，DOC模板请先转换。');
  if(source.size>configuration.max_source_bytes||template.size>configuration.max_template_bytes)return error('文件超限：源文档100 MiB，模板20 MiB。');
  if(!$('max-output-tokens').checkValidity()){$('max-output-tokens').reportValidity();return;}
  const data=new FormData();data.append('source',source);data.append('template',template);
  data.append('settings',JSON.stringify({model:$('model').value,max_output_tokens:Number($('max-output-tokens').value),reasoning_effort:$('reasoning-effort').value,mode:$('mode').value,allow_degraded:$('allow-degraded').checked}));
  error('');clearResult();busy=true;updateStart();
  try{const job=await api('/api/jobs',{method:'POST',headers:{'X-DocTransAI-Token':configuration.token},body:data});renderJob(job);panel('result');poll(job.id);loadHistory(false);}
  catch(e){busy=false;updateStart();error(e.message);}
});
async function boot(){await loadConfiguration(true);await loadHistory();}
boot();
