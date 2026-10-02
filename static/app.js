// Original project UI. Untrusted model/log content is rendered only as text.
const $ = id => document.getElementById(id);
const qualityNames = {fresh:'数据有效',error:'采集异常',stale:'数据过期',no_data:'尚无数据',stopped:'采集停止'};
const toolNames = {collector_status:'检查采集状态',list_ports:'枚举串口',recent_samples:'查询采集记录',compare_config:'核对通信参数',search_manual:'检索参考资料',retest:'三次间隔复测'};
let currentReport = null, busy = false;
async function api(path, body) {
  const r = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
  const value = await r.json(); if(!r.ok) throw new Error(value.error || '请求失败'); return value;
}
function text(tag, value, className) { const e=document.createElement(tag);e.textContent=value;if(className)e.className=className;return e; }
function date(ts) { return new Date(ts*1000).toLocaleTimeString('zh-CN',{hour12:false}); }
function setBusy(value) {busy=value;for(const id of ['diagnose','recheck','apply'])$(id).disabled=value;}
function draw(samples) {
 const canvas=$('chart'),ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;ctx.clearRect(0,0,w,h);
 const rows=samples.slice(-100);const valid=rows.filter(r=>r.ok);let lo=0,hi=100;
 if(valid.length){lo=Math.min(0,...valid.map(r=>r.temperature));hi=Math.max(100,...valid.map(r=>r.temperature));}
 const left=40,right=w-12,top=12,bottom=h-30;
 ctx.font='12px sans-serif';ctx.fillStyle='#8493a2';ctx.strokeStyle='#e8edf2';ctx.lineWidth=1;
 for(let i=0;i<=4;i++){const y=top+(bottom-top)*i/4;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.fillText((hi-(hi-lo)*i/4).toFixed(0),3,y+4);}
 for(const [key,color] of [['temperature','#237aba'],['humidity','#36a08a']]){ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();let open=false;rows.forEach((r,i)=>{if(!r.ok){open=false;return;}const x=left+(right-left)*i/Math.max(1,rows.length-1),y=bottom-(r[key]-lo)/(hi-lo)*(bottom-top);if(open)ctx.lineTo(x,y);else ctx.moveTo(x,y);open=true;ctx.fillStyle=color;ctx.fillRect(x-2,y-2,4,4);});ctx.stroke();}
 if(rows.length){ctx.fillStyle='#8493a2';ctx.fillText(date(rows[0].ts),left,h-7);ctx.fillText(date(rows.at(-1).ts),right-65,h-7);}
}
async function refresh(){try{
 const [state,history]=await Promise.all([api('/api/state'),api('/api/history')]);const s=state.sensor,last=s.last_success;
 $('source').textContent=s.source==='simulation'?'模拟设备 · 非实物实验':'真实串口设备';
 $('provider').textContent=state.provider==='rule_baseline'?'规则基线 · 未连接大模型':`本地模型 · ${state.model}`;
 $('scenario-panel').hidden=s.source!=='simulation';
 $('temperature').textContent=last?last.temperature.toFixed(1)+' ℃':'—';$('humidity').textContent=last?last.humidity.toFixed(1)+' %RH':'—';
 $('temp-meta').textContent=last?'最后成功 '+date(last.ts):'暂无有效记录';$('quality').textContent=qualityNames[s.quality]||s.quality;
 $('quality').className='value small '+(s.quality==='fresh'?'good':'bad');$('age').textContent=s.age_seconds===null?'尚未成功读取':`距最后成功 ${s.age_seconds.toFixed(1)} 秒`;$('streak').textContent=s.consecutive_successes;
 $('notice').className='notice';$('notice').textContent=s.source==='simulation'?'当前使用模拟设备。可测试软件与模型工具调用，不能作为真实硬件联调证据。':'当前连接真实串口。排查建议需结合现场证据，通信超时不能直接判定硬件损坏。';
 $('samples').replaceChildren();for(const r of history.samples.slice(-12).reverse()){const tr=document.createElement('tr');tr.append(text('td',date(r.ts)),text('td',r.ok?'有效':r.code,r.ok?'good':'bad'),text('td',r.ok?r.temperature.toFixed(1):'—'),text('td',r.ok?r.humidity.toFixed(1):'—'));$('samples').append(tr);}draw(history.samples);
 }catch(e){$('notice').className='notice error';$('notice').textContent='无法连接采集服务：'+e.message;$('quality').textContent='服务不可达';$('quality').className='value small bad';}}
function renderReport(r){
 currentReport=r;$('job-status').textContent={queued:'等待执行',running:'正在排查',completed:'本轮完成',failed:'执行失败'}[r.status]||r.status;
 $('trace').replaceChildren();for(const item of r.trace||[]){const d=document.createElement('details');d.className='trace-item';d.append(text('summary',`${item.evidence_id} · ${toolNames[item.tool]||item.tool} · ${item.ok?'完成':'失败'} · ${item.elapsed_ms} ms`),text('pre',JSON.stringify(item.result,null,2)));$('trace').append(d);}
 $('answer').replaceChildren();if(r.error)$('answer').append(text('p',r.error,'bad'));
 if(r.report){$('answer').append(text('p',r.recovery_confirmed?'系统校验：本轮复测满足恢复条件（非长期稳定性结论）':'系统校验：本轮未确认恢复','report-label'));
  if(r.observations?.length){$('answer').append(text('h3','工具直接记录'));const ul=document.createElement('ul');for(const v of r.observations)ul.append(text('li',v.text+' '+v.evidence_ids.join(' · ')));$('answer').append(ul);}
  $('answer').append(text('h3',r.provider==='rule_baseline'?'规则基线解读':'模型解读（含引用，内容尚未经人工核验）'),text('p',r.report.summary,'report-summary'));
  for(const [field,label] of [['findings','引用证据的解读'],['hypotheses','待验证原因'],['next_steps','建议步骤']]){if(!r.report[field]?.length)continue;$('answer').append(text('h3',label));const ul=document.createElement('ul');ul.className='report-list';for(const v of r.report[field]){const li=text('li',typeof v==='string'?v:v.text);if(v.evidence_ids)li.append(text('span',v.evidence_ids.join(' · '),'evidence-id'));ul.append(li);}$('answer').append(ul);}}
 else if(r.status==='running')$('answer').append(text('p','正在执行检查，工具返回结果后会显示在下方。','muted'));
 $('download').disabled=!['completed','failed'].includes(r.status);
}
async function refreshReports(){const {reports}=await api('/api/reports');$('reports').replaceChildren();for(const r of reports){const b=text('button',`${date(r.started)} · ${r.provider==='rule_baseline'?'规则基线':'模型'} · ${r.question.slice(0,45)}`);b.addEventListener('click',()=>{if(!busy)renderReport(r);});$('reports').append(b);}}
async function diagnose(question){if(busy)return;setBusy(true);$('answer').replaceChildren(text('p','开始收集证据…','muted'));try{const {job_id}=await api('/api/diagnose',{question});while(true){const r=await api('/api/jobs/'+job_id);renderReport(r);if(['completed','failed'].includes(r.status))break;await new Promise(resolve=>setTimeout(resolve,600));}await refreshReports();}catch(e){$('answer').replaceChildren(text('p',e.message,'bad'));}finally{setBusy(false);}}
$('question-form').addEventListener('submit',e=>{e.preventDefault();diagnose($('question').value);});
$('recheck').addEventListener('click',()=>diagnose('我已处理现场问题，请重新检查当前状态并进行三次间隔复测，确认是否恢复。'));
$('apply').addEventListener('click',async()=>{try{await api('/api/scenario',{scenario:$('scenario').value});$('scenario-message').textContent='模拟状态已切换。请重新发起排查；此前报告是历史记录。';await refresh();}catch(e){$('scenario-message').textContent=e.message;}});
$('download').addEventListener('click',()=>{if(!currentReport)return;const url=URL.createObjectURL(new Blob([JSON.stringify(currentReport,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='diagnosis-'+currentReport.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
async function poll(){await refresh();setTimeout(poll,2200);}poll();refreshReports().catch(()=>{});
