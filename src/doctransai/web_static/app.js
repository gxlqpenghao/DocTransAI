'use strict';
const $ = id => document.getElementById(id);
let configuration = null, currentJob = null, pollTimer = null, busy = false;
const terminal = new Set(['completed','failed','interrupted']);
const phaseIndex = {queued:0, parsing:0, reading:0, converting:1, auditing:2, publishing:3, completed:4};
const statusLabels = {queued:'准备中',running:'运行中',completed:'已完成',failed:'需要检查',interrupted:'已中断'};

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `请求失败（${response.status}）`);
  return body;
}
function error(message) { $('form-error').textContent = message; $('form-error').hidden = !message; }
function updateStart() { $('start').disabled = busy || !configuration?.ready; $('start').firstElementChild.textContent = busy ? '任务运行中' : '开始转换'; }
async function loadConfiguration(initial=false) {
  try {
    configuration = await api('/api/config');
    $('version').textContent = `v${configuration.version}`;
    $('config-status').replaceChildren(...configuration.checks.map(check => {
      const span=document.createElement('span'); span.className=`check ${check.ok?'good':'bad'}`; span.textContent=check.label+(check.ok?'已配置':'未就绪'); return span;
    }));
    document.querySelector('.environment').classList.toggle('warn', !configuration.ready);
    if (!configuration.ready) $('config-help').open = true;
    if (initial) {
      $('model').value=configuration.defaults.model;
      $('max-output-tokens').value=configuration.defaults.max_output_tokens;
      $('reasoning-effort').value=configuration.defaults.reasoning_effort || 'auto';
    }
    updateStart();
  } catch (e) { $('config-status').textContent='无法连接本地服务，请确认服务仍在运行。'; error(e.message); }
}
function fileChanged(kind) {
  const file=$(kind).files[0];
  $(kind+'-drop').classList.toggle('selected',Boolean(file));
  const size=file && (file.size<1024**2?`${Math.max(1,Math.ceil(file.size/1024))} KiB`:`${(file.size/1024**2).toFixed(2)} MiB`);
  $(kind+'-info').textContent=file ? `${file.name} · ${size}` : '点击选择，或拖拽文件到这里';
  error('');
}
for (const kind of ['source','template']) {
  $(kind).addEventListener('change',()=>fileChanged(kind));
  const area=$(kind+'-drop');
  area.addEventListener('dragover',e=>{e.preventDefault();area.classList.add('dragging');});
  area.addEventListener('dragleave',()=>area.classList.remove('dragging'));
  area.addEventListener('drop',e=>{e.preventDefault();area.classList.remove('dragging');if(e.dataTransfer.files.length===1){$(kind).files=e.dataTransfer.files;fileChanged(kind);}else error('每个位置请选择一份文件。');});
}
$('model').addEventListener('input',()=>{$('reasoning-effort').value='auto';});
$('refresh-config').addEventListener('click',()=>loadConfiguration());
$('close-audit').addEventListener('click',()=>{$('audit-panel').hidden=true;});

function renderJob(job) {
  currentJob=job; busy=!terminal.has(job.status); updateStart();
  $('empty-state').hidden=true; $('job-state').hidden=false;
  $('state-badge').textContent=statusLabels[job.status] || job.status;
  $('state-badge').className='state-badge '+job.status;
  $('task-files').textContent=`${job.source} → ${job.template}`;
  const index=phaseIndex[job.phase] ?? 0;
  document.querySelectorAll('.steps li').forEach((node,i)=>{node.classList.toggle('done',i<index || job.status==='completed');node.classList.toggle('active',i===Math.min(index,3) && job.status!=='completed');});
  $('job-message').textContent=job.message;
  $('job-message').classList.toggle('failed',['failed','interrupted'].includes(job.status));
  const elapsed=Math.max(0,Math.round(((terminal.has(job.status)?job.updated_at:Date.now()/1000)||Date.now()/1000)-job.created_at));
  $('job-time').textContent=`${job.mode==='workspace'?'工作区方式':'ZIP方式'} · ${Math.floor(elapsed/60)}分${elapsed%60}秒`;
  $('quality-warning').hidden=job.parse_quality!=='degraded' && !(job.warnings?.length);
  $('quality-warning').textContent=`上游解析质量：${job.parse_quality || '待确认'}。${job.warnings?.length || 0}条警告已保留，请结合审计复核，不代表解析问题已被修复。`;
  const audit=job.audit || {}, counts=audit.counts || {};
  $('audit-summary').hidden=!audit.status;
  $('audit-state').textContent=audit.status==='assessed'?'已完成字段核对':'审计未完成 · 保守台账';
  $('high-count').textContent=counts.filled_high || 0; $('low-count').textContent=counts.filled_low || 0; $('empty-count').textContent=counts.unfilled || 0;
  const actions=$('result-actions'); actions.replaceChildren();
  for (const file of job.files || []) {
    if (file.name==='audit.html') {
      const button=document.createElement('button');button.type='button';button.textContent='查看字段审计 ↗';
      button.addEventListener('click',()=>{$('audit-frame').src=file.url;$('audit-panel').hidden=false;$('audit-panel').scrollIntoView({behavior:'smooth',block:'start'});});actions.append(button);
    } else {
      const labels={'result.docx':'下载转换文档','result.xlsx':'下载转换表格','audit.json':'审计JSON','review.json':'诊断报告','integration.json':'任务记录','workspace-export.zip':'工作区导出包'};
      const link=document.createElement('a'); link.href=file.url; link.download=file.name;link.textContent=labels[file.name] || file.name;
      if(file.name.startsWith('result.')){link.className='main-download';if(job.status!=='completed')link.textContent+='（待复核）';} actions.append(link);
    }
  }
  $('task-ids').textContent=`本地任务：${job.id}\n解析任务：${job.job_id || '等待创建'}\n工作区：${job.workspace_id || '未创建'}`;
  $('events').replaceChildren(...(job.events || []).map(event=>{const li=document.createElement('li');li.textContent=`${new Date(event.at*1000).toLocaleTimeString()} · ${event.message}`;return li;}));
}
async function poll(jobId) {
  clearTimeout(pollTimer);
  try {
    const job=await api('/api/jobs/'+jobId);renderJob(job);
    if(!terminal.has(job.status))pollTimer=setTimeout(()=>poll(jobId),2000);
    else await loadHistory(false);
  } catch (e) {
    $('job-message').textContent='暂时无法读取进度，任务可能仍在运行。正在重新连接…';
    pollTimer=setTimeout(()=>poll(jobId),5000);
  }
}
async function loadHistory(restore=true) {
  try {
    const {jobs}=await api('/api/jobs');$('history-count').textContent=jobs.length;
    $('history-list').replaceChildren(...jobs.map(job=>{
      const button=document.createElement('button');button.type='button';button.textContent=`${statusLabels[job.status] || job.status} · ${job.source}`;
      button.disabled=busy && currentJob?.id!==job.id;
      button.addEventListener('click',()=>{clearTimeout(pollTimer);$('audit-panel').hidden=true;poll(job.id);});return button;
    }));
    if(restore && jobs.length)poll((jobs.find(j=>!terminal.has(j.status)) || jobs[0]).id);
  } catch (e) { error('无法读取历史任务：'+e.message); }
}
$('conversion-form').addEventListener('submit', async e=>{
  e.preventDefault(); if(busy || !configuration?.ready)return;
  const source=$('source').files[0], template=$('template').files[0];
  if(!source || !template)return error('请选择源文档和目标模板。');
  if(!/\.(docx|xlsx)$/i.test(template.name))return error('目标模板仅支持DOCX或XLSX，DOC模板请先转换为DOCX。');
  if(source.size>configuration.max_source_bytes || template.size>configuration.max_template_bytes)return error('文件超过大小上限：源文档100 MiB，模板20 MiB。');
  const data=new FormData();data.append('source',source);data.append('template',template);data.append('instruction',$('instruction').value);
  data.append('settings',JSON.stringify({model:$('model').value, max_output_tokens:Number($('max-output-tokens').value),reasoning_effort:$('reasoning-effort').value, mode:$('mode').value, allow_degraded:$('allow-degraded').checked}));
  error('');busy=true;updateStart();$('submit-note').textContent='正在上传文件到本地后端…';
  try {
    const job=await api('/api/jobs',{method:'POST',headers:{'X-DocTransAI-Token':configuration.token},body:data});
    $('audit-panel').hidden=true;renderJob(job);poll(job.id);loadHistory(false);
  } catch(e) {busy=false;updateStart();error(e.message);} finally {$('submit-note').textContent='模板原件不会被修改';}
});
async function boot(){await loadConfiguration(true);await loadHistory();}
boot();
