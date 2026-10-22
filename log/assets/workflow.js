// Live projection only: this view never schedules, retries or sends a message.
const workflow = {data:null, selected:'', scope:'active', expanded:new Set(), paused:false,
  timer:null, controller:null, epoch:0, busy:false, baseline:false, error:'', signature:'',
  lastSuccess:0, pulses:[]};
const WF_STATUS = {unbatched:'等待合并',ready:'等待提交',processing:'处理中',waiting_delivery:'回复已就绪',
  pending:'等待发送',sending:'分批输入中',confirming:'等待气泡确认',sent:'已确认发送',
  blocked:'已阻断',uncertain:'结果不确定',waiting_blocker:'等待旧任务释放',discarded:'已丢弃',
  model_failed:'模型失败已结束',no_reply:'本轮无需回复'};
const WF_COLORS = ['#72b4ff','#bb9aff','#51d4b1','#f0bc76','#f18db0'];
function workflowColor(m){let h=0;for(const c of m.uid+'|'+m.members.join('|'))h=(h*31+c.charCodeAt(0))>>>0;return WF_COLORS[h%WF_COLORS.length];}
function workflowMatches(m){return matchesQuery(m.contact,m.uid,m.label,m.members.join(' '),m.request_id,m.id,m.inbox_ids.join(' '),m.preview,m.reply_preview,m.error);}
function workflowSignature(data){return JSON.stringify(data.messages.map(m=>[m.id,m.stage,m.status,m.scope,m.preview,m.reply_preview,m.error,m.uid,m.members,m.attempts,m.part_count,m.sent_parts,m.retry_at,m.discard_at,m.reason,m.events.map(e=>e.key)]))+JSON.stringify(data.counts)+JSON.stringify(data.sources);}
function workflowFresh(previous,next,baseline){
  if(!previous||!baseline)return [];
  const old=new Set(previous.messages.flatMap(m=>m.events.map(e=>e.key)));
  // Late snapshots of old history are not fresh transmissions.
  const fresh=next.messages.flatMap(m=>m.events.filter(e=>!old.has(e.key)&&e.ts>=previous.at).map(e=>({m,e})));
  for(const m of next.messages){
    const prior=previous.messages.find(p=>p.id===m.id);
    if(prior&&(prior.stage!==m.stage||prior.status!==m.status||prior.delivery_id!==m.delivery_id)&&!fresh.some(x=>x.m.id===m.id&&x.e.node===m.stage)){
      const evidence=m.events.findLast(e=>e.node===m.stage);
      if(evidence)fresh.push({m,e:evidence});
    }
  }
  return fresh;
}
function stopWorkflow(){
  workflow.epoch++;clearTimeout(workflow.timer);workflow.controller?.abort();workflow.controller=null;
  workflow.busy=false;workflow.baseline=false;stopWorkflowPulses();
}
function startWorkflow(){
  workflow.signature='';workflow.error='';workflow.baseline=false;
  renderWorkflow(true);loadWorkflow();
}
async function loadWorkflow(){
  if(state.tab!=='workflow'||workflow.busy)return;
  clearTimeout(workflow.timer);
  if(document.hidden){workflow.baseline=false;stopWorkflowPulses();workflow.timer=setTimeout(loadWorkflow,1000);return;}
  const epoch=workflow.epoch,controller=new AbortController();workflow.controller=controller;workflow.busy=true;
  const timeout=setTimeout(()=>controller.abort(),5000);
  try{
    const response=await fetch('/api/workflow',{signal:controller.signal,cache:'no-store'});
    if(!response.ok)throw new Error(response.status===404?'工作流接口尚未加载，请手动重启 log 服务后刷新页面':'读取失败（HTTP '+response.status+'）');
    const data=await response.json();
    if(epoch!==workflow.epoch||state.tab!=='workflow')return;
    if(data.status!=='ok')throw new Error(data.error||'队列尚不可读取');
    const fresh=workflowFresh(workflow.data,data,workflow.baseline);
    const oldSelected=workflow.data?.messages.find(m=>m.id===workflow.selected);
    if(oldSelected&&!data.messages.some(m=>m.id===workflow.selected)){
      workflow.selected=data.messages.find(m=>m.inbox_ids.some(id=>oldSelected.inbox_ids.includes(id)))?.id||'';
    }
    const recovered=!!workflow.error;workflow.data=data;workflow.error='';workflow.lastSuccess=Date.now();workflow.baseline=true;
    renderWorkflow(recovered);updateWorkflowClock();
    if(!workflow.paused)pulseWorkflow(fresh);
    markRefreshed();
  }catch(error){
    if(epoch!==workflow.epoch||state.tab!=='workflow')return;
    workflow.error=error.name==='AbortError'?'读取超时，正在重连':error instanceof TypeError?'无法连接 log 服务':error.message;
    workflow.baseline=false;stopWorkflowPulses();renderWorkflow(true);updateWorkflowClock();
  }finally{
    clearTimeout(timeout);
    if(epoch===workflow.epoch&&state.tab==='workflow'){
      workflow.busy=false;workflow.controller=null;workflow.timer=setTimeout(loadWorkflow,1000);
    }
  }
}
function stopWorkflowPulses(){
  workflow.pulses.forEach(clearTimeout);workflow.pulses=[];
  document.querySelectorAll('.wf-pulse').forEach(el=>el.classList.remove('wf-pulse'));
}
function pulseWorkflow(events){
  if(workflow.paused||workflow.error||!events.length)return;
  const targets=new Map();
  for(const {m,e} of events){
    targets.set('wf-node-'+workflowService(e.node),workflowColor(m));
    const edge=workflowEventEdge(e);if(edge)targets.set('wf-edge-'+edge,workflowColor(m));
  }
  for(const [id,color] of targets){
    const el=$('#'+id);
    if(el){
      el.style.setProperty('--packet-color',color);
      el.classList.remove('wf-pulse');void el.offsetWidth;el.classList.add('wf-pulse');
      workflow.pulses.push(setTimeout(()=>el.classList.remove('wf-pulse'),950));
    }
  }
  // Keep the cleanup list bounded during long-running monitoring sessions.
  if(workflow.pulses.length>40)workflow.pulses.splice(0,workflow.pulses.length-40).forEach(clearTimeout);
}
function updateWorkflowClock(){
  const live=$('#wf-live');if(!live)return;
  live.textContent=workflow.error?'数据已过期 · 自动重连':workflow.lastSuccess?'实时读取 · 1 秒':'正在连接';
  live.classList.toggle('stale',!!workflow.error);
  $('#wf-updated').textContent=workflow.lastSuccess?'最近成功读取 '+new Date(workflow.lastSuccess).toLocaleTimeString('zh-CN',{hour12:false}):'尚无成功读取';
  const at=(workflow.data?.at||0)+(workflow.error?0:(Date.now()-workflow.lastSuccess)/1000);
  document.querySelectorAll('[data-wf-deadline]').forEach(el=>{
    const remaining=Math.max(0,Math.ceil(Number(el.dataset.wfDeadline)-at));
    el.textContent=remaining>0?remaining+' 秒': '等待调度执行';
  });
}
function workflowIdentity(m){return `<span class="wf-identity">UID <code>${esc(m.uid)}</code>${m.group?'<b>群聊</b>':''}</span>`+
  (m.group?`<span class="wf-member">成员 ${m.members.length?m.members.map(esc).join(' / '):'未记录'}</span>`:'');}
function workflowRecovery(m){
  return `${m.attempts?`<span>已尝试 ${m.attempts} 次 · 重试 ${Math.max(0,m.attempts-1)} 次</span>`:''}`+
    (m.retry_at?`<span>自动重试：<b data-wf-deadline="${m.retry_at}"></b></span>`:'')+
    (m.discard_at&&!m.terminal?`<span>失败到期释放：<b data-wf-deadline="${m.discard_at}"></b></span>`:'');
}
function workflowCard(m,compact=false){
  return `<button class="wf-message ${compact?'compact':''} ${m.scope==='issues'?'issue':''} ${workflow.selected===m.id?'selected':''}" data-focus-key="wf-${compact?'node':'feed'}-${esc(m.id)}" data-wf-select="${esc(m.id)}" style="--identity:${workflowColor(m)}" aria-label="查看 ${esc(m.contact)} 消息 ${esc(m.id)}">
    <span class="wf-message-head"><strong>${esc(m.contact)}</strong><span>${esc(WF_STATUS[m.status]||m.status)}</span></span>
    ${workflowIdentity(m)}<span class="wf-preview">${esc(m.stage>=5&&m.reply_preview?m.reply_preview:m.preview)}</span>
    <span class="wf-meta">${m.kind==='push'?'主动推送':m.message_count+' 条收件'} · ${m.request_id?'请求 '+esc(m.request_id.slice(0,10)):m.kind==='push'?'发件 '+esc(m.delivery_id):'收件 #'+esc(m.inbox_ids.join(', #'))}${m.part_count?' · 已发 '+m.sent_parts+'/'+m.part_count+' 句':''}</span>
    ${m.error?`<span class="wf-error">${esc(m.error)}</span>`:''}<span class="wf-recovery">${workflowRecovery(m)}</span></button>`;
}
function workflowTrace(m){
  const grouped=groupFlowEvents(m.events);
  const diagnostics=JSON.stringify({request_id:m.request_id,record_id:m.id,inbox_ids:m.inbox_ids,delivery_id:m.delivery_id,events:m.events},null,2);
  return `<div class="wf-inspect" style="--identity:${workflowColor(m)}"><div class="row"><b>${esc(m.contact)} · 流转详情</b><button id="wf-deselect" aria-label="取消消息选择">×</button></div>
    ${workflowIdentity(m)}<div class="wf-meta">${esc(full(m.at))} · 当前：${esc(WF_STATUS[m.status]||m.status)}</div>
    <div class="wf-fulltext">${esc(m.preview)}</div>
    ${m.error?`<p class="wf-error">${esc(m.error)}</p>`:''}<div class="wf-recovery">${workflowRecovery(m)}</div>
    ${m.reason.record_id&&m.reason.record_id!==m.request_id?`<div class="wf-meta">关联任务：<code>${esc(m.reason.record_id)}</code></div>`:''}
    <ol class="wf-trace">${grouped.map(e=>`<li class="${['error','failed','blocked','uncertain','skipped'].includes(e.status)?'bad':''}"><time>${e.time_unknown?'时间未记录':esc(hm(e.ts))+':'+p2(new Date(e.ts*1000).getSeconds())}</time><div><b>${esc(FLOW_STAGE_LABELS[e.stage]||e.stage)}</b><small>${esc(FLOW_STATUS_LABELS[e.status]||e.status)}${!e.time_unknown&&e.elapsed_ms!=null?' · '+(e.elapsed_ms/1000).toFixed(2)+' 秒':''}${e.tool?' · '+esc(e.tool):''}</small></div></li>`).join('')}</ol>
    ${m.events_truncated?'<p class="wf-note">此处保留最近 200 条事件，完整记录见消息流转。</p>':''}
    <p class="wf-note">未记录的阶段保持未确认；动画只表示新事件到达。</p>
    <details data-detail="workflow:${esc(m.id)}"><summary>诊断详情 · 完整 ID 与事件</summary><pre class="pre">${esc(diagnostics)}</pre></details>
    <button id="wf-diagnose">在收发队列中查看 / 处理</button></div>`;
}
// Backend stages remain precise; multiple stages share one physical service node.
function workflowService(stage){return ['wxbot','inbox','butler','model','butler','outbox','wxbot','wxbot'][stage]||'butler';}
function workflowEventEdge(e){
  if(e.stage==='wxbot_inbox')return 'receive';
  if(['wxbot_butler','butler_received'].includes(e.stage))return 'dispatch';
  if(e.stage==='hermes_request')return 'request';
  if(e.stage==='hermes_result'&&['ok','completed'].includes(e.status))return 'result';
  if(e.stage==='wxbot_result'&&e.status==='ok')return 'enqueue';
  if(e.stage==='wechat_submitted'||(e.stage==='wechat_delivery'&&['sending','confirming','sent'].includes(e.status)))return 'send';
  return '';
}
function workflowSummaryRow(m,variant){
  const tool=m.events.findLast(e=>e.stage==='hermes_tool');
  const text=m.stage>=5&&m.reply_preview?m.reply_preview:m.preview;
  const status=m.scope==='issues'||m.terminal?(WF_STATUS[m.status]||m.status):({2:'接收 / 调度',4:'完整结果就绪'}[m.stage]||WF_STATUS[m.status]||m.status);
  return `<button class="wf-summary-row ${workflow.selected===m.id?'selected':''} ${m.scope==='issues'?'issue':''}" data-wf-select="${esc(m.id)}" data-focus-key="wf-node-${esc(m.id)}" style="--identity:${workflowColor(m)}" aria-label="查看 ${esc(m.contact)} 消息 ${esc(m.id)}">
    <span class="wf-row-text"><strong>${esc(m.contact)}</strong><span class="wf-row-content"> · ${esc(text)}</span></span>
    <span class="wf-row-sub"><span class="wf-row-uid">UID ${esc(m.uid)}${m.group?' / 成员 '+esc(m.members.join(', ')||'未记录'):''}</span><span>${esc(status)}${m.part_count?' · '+m.sent_parts+'/'+m.part_count+' 句':''}</span></span>
    ${variant==='model'?`<span class="wf-model-progress">${tool?'工具 '+esc(tool.tool||'未知')+' · '+esc(FLOW_STATUS_LABELS[tool.status]||tool.status):'等待模型过程事件'} · 请求 ${esc(m.request_id.slice(0,10)||m.id)}</span>`:''}
    ${m.error?`<span class="wf-row-error">${esc(m.error)}</span>`:''}${m.scope==='issues'?`<span class="wf-recovery">${workflowRecovery(m)}</span>`:''}</button>`;
}
function workflowDiagram(data,visible,selected,recent){
  const trail=new Set((selected?.events||[]).map(e=>workflowService(e.node)));
  const edges=new Set((selected?.events||[]).map(workflowEventEdge));
  const present=visible.filter(m=>!m.terminal||m.id===workflow.selected||recent.has(m.id));
  const model=data?.backend==='hermes'?'Hermes':data?.backend==='codex'?'Codex':'模型';
  function node(id,title,subtitle,icon){
    const messages=present.filter(m=>workflowService(m.stage)===id).sort((a,b)=>a.order-b.order||a.id.localeCompare(b.id));
    const cap=['butler','wxbot'].includes(id)?2:8;
    const shown=workflow.expanded.has(id)?messages:messages.slice(0,cap);
    return `<div id="wf-node-${id}" data-service="${id}" class="wf-node wf-service-${id} ${trail.has(id)?'traced':''} ${selected&&workflowService(selected.stage)===id?'current':''}">
      <div class="wf-node-label"><span class="wf-service-icon">${icon}</span><div><h3>${esc(title)}</h3><p>${esc(subtitle)}</p></div><span class="wf-service-count">${messages.length} <small>${id==='model'?'条请求':'条'}</small></span></div>
      <div class="wf-node-messages">${shown.map(m=>workflowSummaryRow(m,id)).join('')||`<div class="wf-service-empty">${id==='model'?'等待新的模型请求':id==='inbox'?'暂无待合并或待提交消息':id==='outbox'?'暂无等待发送的回复':id==='butler'?'接收、调度与回复共用此节点':'接收消息 · 输入回复 · 确认发送'}</div>`}</div>
      ${messages.length>cap?`<button class="wf-more" data-wf-more="${id}">${workflow.expanded.has(id)?'收起':'查看其余 '+(messages.length-cap)+' 条'}</button>`:''}</div>`;
  }
  function wires(band,paths){
    return `<div class="wf-wire-band wf-band-${band}"><svg viewBox="0 0 1000 72" preserveAspectRatio="none" aria-hidden="true"><defs><marker id="wf-arrow-${band}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>${paths.map(([id,path,label])=>`<g id="wf-edge-${id}" class="wf-wire ${edges.has(id)?'traced':''}" style="--trace-color:${selected?workflowColor(selected):'#5d978e'}"><path class="wf-wire-line" d="${path}" marker-end="url(#wf-arrow-${band})"/><path class="wf-packet" d="${path}" pathLength="100"/></g>`).join('')}</svg>${paths.map(([id,path,label],i)=>`<span class="wf-wire-label ${i?'right':'left'}">${label}</span>`).join('')}</div>`;
  }
  return `<div class="wf-diagram">${node('model',model,'模型执行区 · 多用户请求与工具进度','✦')}
    ${wires('model',[['request','M420 72 V2','↑ 请求模型'],['result','M580 0 V70','↓ 完整回复']])}
    <div class="wf-hub-row">${node('butler','Butler','身份 · 角色 · 权限 · 调度','B')}</div>
    ${wires('queues',[['dispatch','M240 72 V38 H420 V2','↑ 提交收件'],['enqueue','M580 0 V38 H760 V70','↓ 回复入队']])}
    <div class="wf-queue-pair">${node('inbox','收件队列','wxbot · 合并连续消息 / 等待提交','收')}${node('outbox','发件队列','wxbot · 按会话顺序发送','发')}</div>
    ${wires('wechat',[['receive','M420 72 V38 H240 V2','↑ 收到消息'],['send','M760 0 V38 H580 V70','↓ 发送回复']])}
    <div class="wf-hub-row">${node('wxbot','wxbot','微信收件与发送确认','W')}</div></div>`;
}
function renderWorkflow(force=false){
  if(state.tab!=='workflow')return;
  const data=workflow.data;
  const recent=new Set((data?.messages||[]).filter(m=>m.terminal&&data.at-m.updated_at<15).map(m=>m.id));
  const signature=(data?workflowSignature(data):'empty')+'|'+[...recent].join(',')+'|'+workflow.selected+'|'+workflow.scope+'|'+currentQuery()+'|'+[...workflow.expanded].join(',')+'|'+workflow.error;
  if(!force&&signature===workflow.signature)return;
  workflow.signature=signature;
  const all=data?.messages||[],visible=all.filter(workflowMatches),selected=all.find(m=>m.id===workflow.selected);
  const count=data?.counts||{};
  const diagram=workflowDiagram(data,visible,selected,recent);
  const scoped=visible.filter(m=>workflow.scope==='active'?!m.terminal:m.scope===workflow.scope)
    .sort((a,b)=>workflow.scope==='active'?a.at-b.at||a.id.localeCompare(b.id):b.updated_at-a.updated_at||b.id.localeCompare(a.id));
  const events=visible.flatMap(m=>m.events.map(e=>({m,e}))).sort((a,b)=>b.e.ts-a.e.ts).slice(0,6);
  const warnSources=(data?.sources||[]).filter(s=>s.status!=='ok'||s.truncated);
  const scrolls=['.wf-feed','.wf-inspect',...['model','inbox','outbox','butler','wxbot'].map(id=>'#wf-node-'+id+' .wf-node-messages')].map(selector=>[selector,$(selector)?.scrollTop||0]);
  $('#pane').innerHTML=`<div class="wf-shell ${workflow.paused?'animation-paused':''} ${workflow.error?'disconnected':''}">
    <div class="wf-top"><div><span id="wf-live" class="wf-live">正在连接</span><span id="wf-updated" class="wf-note"></span></div><button id="wf-animation" aria-pressed="${workflow.paused}">${workflow.paused?'恢复动画':'暂停动画'}</button></div>
    <div class="wf-stats">${[['待处理轮次',count.active],['待合并收件',count.inbox],['等待模型',count.model],['待发送分句',count.outbox],['异常任务',count.issues]].map(([label,value],i)=>`<div class="${i===4&&value?'attention':''}"><span>${label}</span><strong>${value??'—'}</strong><small>${i===4?'当前需要关注':i===2?'已领取，等待完整结果':'全部会话'}</small></div>`).join('')}</div>
    ${workflow.error?`<div class="wf-alert" role="status">${esc(workflow.error)}${data?' · 下方保留最近快照，状态及倒计时已暂停。':''}</div>`:''}
    ${warnSources.length?`<div class="wf-note wf-source-note">${warnSources.map(s=>esc(s.name)+(s.status==='missing'?' 过程日志尚未创建':s.status!=='ok'?' 过程日志暂不可读取':' 仅载入最近 4 MB 过程事件')).join('；')}。队列中已确认的阶段仍会显示。</div>`:''}
    ${data?.active_more?'<div class="wf-alert">当前展示最早的 500 条待处理记录。更多记录请在收发队列分页查看。</div>':''}
    <div class="wf-layout"><div class="wf-canvas"><div class="wf-section-heading"><h2>消息工作流</h2><span>进线与出线分开 · 服务节点共用</span></div>${diagram}<div class="wf-legend"><i></i> 新事件传输 <em></em> 所选消息经过的路径 <span>同一用户保持同一颜色</span></div></div>
    <div class="wf-sidebar"><div class="wf-section-heading"><h2>实时消息</h2><span>${visible.length} 条已载入</span></div>
      <div class="wf-tabs">${[['active','进行中'],['issues','异常'],['complete','已完成']].map(([value,label])=>`<button data-wf-scope="${value}" class="${workflow.scope===value?'on':''}">${label} <b>${visible.filter(m=>value==='active'?!m.terminal:m.scope===value).length}</b></button>`).join('')}</div>
      ${selected?workflowTrace(selected):'<div class="wf-select-hint">点选消息，查看身份、耗时与完整流转路径。</div>'}
      <div class="wf-feed">${scoped.map(m=>workflowCard(m)).join('')||'<div class="empty">没有匹配的消息</div>'}</div>
      <p class="wf-note">当前载入的消息可按用户、UID、群成员及 ID 搜索。${data?.history_more?'历史仅显示最近 60 轮，更多见消息流转。':'历史不会重复进入工作流。'}</p></div></div>
    <details class="wf-recent" data-detail="workflow-recent"><summary>最近事件 · ${events.length?esc(full(events[0].e.ts)):'等待收件'}</summary>${events.map(({m,e})=>`<div><time>${esc(full(e.ts))}</time><b>${esc(m.contact)}</b><span>${esc(FLOW_STAGE_LABELS[e.stage]||e.stage)} · ${esc(FLOW_STATUS_LABELS[e.status]||e.status)}</span></div>`).join('')}</details></div>`;
  $('#wf-animation').onclick=()=>{workflow.paused=!workflow.paused;stopWorkflowPulses();renderWorkflow(true);};
  $('#pane').querySelectorAll('[data-wf-select]').forEach(button=>button.onclick=()=>{workflow.selected=button.dataset.wfSelect;renderWorkflow(true);});
  $('#pane').querySelectorAll('[data-wf-scope]').forEach(button=>button.onclick=()=>{workflow.scope=button.dataset.wfScope;renderWorkflow(true);});
  $('#pane').querySelectorAll('[data-wf-more]').forEach(button=>button.onclick=()=>{const id=button.dataset.wfMore;workflow.expanded.has(id)?workflow.expanded.delete(id):workflow.expanded.add(id);renderWorkflow(true);});
  if(selected){$('#wf-deselect').onclick=()=>{workflow.selected='';renderWorkflow(true);};
    $('#wf-diagnose').onclick=()=>{state.qContact=selected.contact;state.qState='all';state.qScope=selected.terminal?'history':selected.scope==='issues'?'issues':'active';resetQueuePages();switchTab('queue');};}
  for(const [selector,top] of scrolls){const node=$(selector);if(node)node.scrollTop=top;}
  updateWorkflowClock();
}
document.addEventListener('visibilitychange',()=>{
  if(state.tab!=='workflow')return;
  if(document.hidden){workflow.baseline=false;stopWorkflowPulses();}
  else loadWorkflow();
});
