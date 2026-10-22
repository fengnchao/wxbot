/* ---------------- wxbot 通道 ---------------- */
const hhmmss = s => (s||'').slice(11,19);
const daystr = s => (s||'').slice(0,10);
const sec1 = n => (n==null? '' : Number(n).toFixed(1));

async function loadWxbot(){
  const request=++state.wRequest;
  const params=new URLSearchParams({flow_contact:state.wUid==='all'?'':state.wUid,flow_offset:String(state.wFlowOffset),flow_order:state.wOrder});
  try{
    const data = await get('/api/wxbot?'+params);
    if(request!==state.wRequest) return;
    state.wdata = data;
  }catch(e){
    if(state.tab!=='wxbot'||request!==state.wRequest) return;
    $('#pane').innerHTML = '<div class="empty">载入失败：'+esc(e.message||e)+'</div>';
    return;
  }
  if(state.tab!=='wxbot') return;
  renderWxNav();
  renderWxPane();
}

function renderWxNav(){
  const d = state.wdata, el = $('#list'), st = d.stats;
  const head = `<div class="user ${state.wUid==='all'?'sel':''}" data-u="all">
      <div class="nm">全部联系人</div>
      <div class="st"><span>事件 <b>${st.events}</b></span><span>收到 ${st.received}</span>
        <span>回复 ${st.reply}</span><span>外发 ${st.outbound}</span></div>
      <div class="st">${st.slow_rounds?`<span class="warn">慢轮(&gt;300s) ${st.slow_rounds}</span>`:''}
        ${st.timeouts?`<span class="warn">超时 ${st.timeouts}</span>`:''}
        <span>任务推断 ${st.inferred_tasks}</span></div>
    </div>`;
  el.innerHTML = head + d.contacts.slice().sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).map(c=>`
    <div class="user ${state.wUid===c.uid?'sel':''}" data-u="${esc(c.uid)}">
      <div class="nm">${esc(c.name)}${c.window?` <span class="sbadge ${c.window==='connected'?'sb-ok':'sb-timeout'}">${c.window==='connected'?'窗口在线':'窗口未开'}</span>`:''}</div>
      <div class="uid">${esc(c.user_id||c.uid)}${c.profile?` · ${esc(c.profile)}`:''}</div>
      <div class="st"><span>事件 <b>${c.count}</b></span><span>外发 ${c.out}</span>
        ${c.flow_count?`<span>流转 ${c.flow_count}</span>`:''}
        ${['blocked','uncertain'].includes(c.flow_reason)?'<span class="warn">队列阻塞</span>':''}
        ${c.slow?`<span class="warn">慢轮 ${c.slow}</span>`:''}</div>
    </div>`).join('');
  el.querySelectorAll('.user').forEach(n=>n.onclick=()=>{
    state.wUid = n.dataset.u; state.wFlowOffset=0;
    el.querySelectorAll('.user').forEach(x=>x.classList.toggle('sel', x.dataset.u===state.wUid));
    loadWxbot();
  });
}

function wxMeta(e){
  const bits = [];
  if(e.elapsed_s!=null){
    const sl = e.elapsed_s>300 && e.elapsed_kind!=='session';
    const lbl = e.elapsed_kind==='session' ? '会话累计耗时（非本轮）' : '调用 agent 耗时';
    bits.push(`<span>${lbl} <b class="${sl?'slow':''}">${sec1(e.elapsed_s)}s</b>${sl?' <span class="sbadge sb-error">慢</span>':''}</span>`);
  }
  if(e.reply_wait_s!=null) bits.push(`<span class="k">收到→回复 ${sec1(e.reply_wait_s)}s</span>`);
  if(e.status==='timeout') bits.push('<span class="sbadge sb-timeout">超时</span>');
  else if(e.status==='error') bits.push('<span class="sbadge sb-error">出错</span>');
  else if(e.status==='ok') bits.push('<span class="sbadge sb-ok">ok</span>');
  if(e.agent){
    bits.push(`<span class="k">session ${esc(e.agent.session_id)}</span>`);
    bits.push(`<span class="k">${e.agent.api_call_count} 次 API 调用</span>`);
    bits.push(`<span class="k">${e.agent.tool_call_count} 次工具调用</span>`);
  }
  return bits.join('');
}

function wxEvent(e){
  const t = `<div class="t">${hhmmss(e.time)}</div>`;
  if(e.direction==='system'){
    const txt = (e.content||'').trim();
    if(!txt) return '';
    return `<div class="m sysline">${t}<div class="b"><div class="bubble">· ${esc(txt)}</div></div></div>`;
  }
  if(e.direction==='api_error'){
    return `<div class="m err">${t}<div class="b">
      <div class="lbl">模型运行时 API 调用失败</div>
      <div class="bubble">${esc(e.content)}</div></div></div>`;
  }
  if(e.direction==='outbound'){
    const tk = e.task || {};
    const badge = tk.job_id
      ? `<span class="sbadge sb-task">任务 ${esc(tk.name)}</span><span class="sbadge sb-infer">推断</span><span class="k">job ${esc(tk.job_id)}</span>`
      : `<span class="sbadge sb-manual">${esc(tk.name||'管家 / 手动推送')}</span>`;
    const sent = e.sent_time ? `<span class="k">已发出 ${hhmmss(e.sent_time)}</span>` : '';
    return `<div class="m exp">${t}<div class="b">
      <div class="lbl">外发（wxbot 通道）</div>
      <div class="bubble">${esc(e.content)}</div>
      <div class="meta">${badge}${sent}</div></div></div>`;
  }
  const cls = e.direction==='received' ? 'in' : 'out';
  const lbl = e.direction==='received'
      ? `收到 · ${esc(e.name)} (${esc(e.uid)})` : '机器人回复';
  return `<div class="m ${cls}">${t}<div class="b">
    <div class="lbl">${lbl}</div>
    <div class="bubble">${esc(e.content)}</div>
    <div class="meta">${wxMeta(e)}</div></div></div>`;
}

const FLOW_STAGE_LABELS={wxbot_received:'wxbot 确认收件入库',wxbot_inbox:'进入收件队列',wxbot_merge:'连续消息合并',
  wxbot_model:'模型工作线程领取',wxbot_butler:'wxbot 请求 Butler',butler_received:'Butler 确认收到',
  butler_session:'Butler 会话锁',hermes_request:'Butler 请求 模型运行时',hermes_generating:'模型运行时 生成回复',
  hermes_tool:'模型运行时 工具执行',hermes_status:'模型运行时 过程事件',hermes_approval:'模型运行时 等待审批',
  hermes_result:'模型运行时 完整结果',butler_action:'Butler 行动执行',butler_result:'Butler 结果就绪',
  wxbot_result:'wxbot 完整回复入发件箱',wxbot_outbox:'回复分句入队',wechat_submitted:'微信已按回车',wechat_delivery:'微信分句发送'};
const FLOW_STATUS_LABELS={ok:'完成',started:'已开始，等待确认',accepted:'接口已接受',waiting:'等待中',
  running:'执行中',completed:'执行结束',failed:'失败',error:'失败',blocked:'已阻塞',uncertain:'结果不确定',
  unconfirmed:'未记录 / 未确认',not_started:'未提交',pending:'待发送',sending:'键入中',confirming:'发送确认中',sent:'已确认发送',skipped:'已跳过 / 丢弃'};
function groupFlowEvents(events){
  const groups=new Map();
  const pending=new Map();let occurrence=0;
  for(const e of events){
    const base=[e.stage,e.tool||'',e.tool_call_id||'',e.part_seq||'',e.delivery_id||'',e.attempt||''].join(':');
    let key=base;
    if(e.stage==='hermes_tool'&&!e.tool_call_id){
      const active=pending.get(base)||[];
      if(['started','running'].includes(e.status)){
        key=base+':occurrence:'+occurrence++;
        if(active.length){active.forEach(id=>groups.get(id).ambiguous=true);}
        groups.set(key,{...e,firstTs:e.ts,ambiguous:!!active.length});
        active.push(key);pending.set(base,active);continue;
      }
      if(active.length===1&&!groups.get(active[0]).ambiguous)key=active[0];
      else key=base+':event:'+occurrence++;
      if(['completed','ok','failed','error','blocked','uncertain'].includes(e.status))active.shift();
      pending.set(base,active);
    }
    if(!groups.has(key))groups.set(key,{...e,start:e.ts,firstTs:e.ts});
    else{
      const row=groups.get(key),first=row.firstTs;
      Object.assign(row,e);row.firstTs=first;
      if(e.elapsed_ms==null&&e.ts!=null&&first!=null)row.elapsed_ms=Math.max(0,(e.ts-first)*1000);
    }
  }
  return [...groups.values()].sort((a,b)=>(a.firstTs??Infinity)-(b.firstTs??Infinity));
}
function currentFlowStage(events){
  return events.filter(e=>!['not_started','not_submitted','unconfirmed','missing'].includes(e.status)).at(-1)?.stage||'';
}
function renderMessageFlow(data){
  if(!data) return '';
  if(data.status!=='ok') return `<div class="head"><h2>消息流转记录</h2><div class="warn">${esc(data.error||'无法读取')}</div></div>`;
  let flows=(data.flows||[]).filter(f=>(state.wUid==='all'||f.contact===state.wUid)&&matchesQuery(f.contact,f.preview,f.state,f.reason?.error,f.reason?.message,f.request_id));
  const cards=flows.map((f,i)=>{
    const reason=f.reason||{},bad=['blocked','uncertain','model_failed'].includes(reason.code)||['blocked','uncertain','model_failed'].includes(f.state);
    const events=groupFlowEvents(f.events||[]).map(e=>{
      const failed=['error','failed','blocked','uncertain'].includes(e.status);
      const errorNote={missing_final_response:'缺少最终正文事件，请更新并重启 模型运行时',invalid_stream:'模型运行时 过程流无效或未完整结束'}[e.error_code];
      const bits=[e.tool&&('工具 '+e.tool),e.tool_call_id&&('调用 '+e.tool_call_id),
        e.http_status&&('HTTP '+e.http_status),e.elapsed_ms!=null&&('耗时 '+(e.elapsed_ms/1000).toFixed(2)+'s'),
        e.error_type&&('错误 '+e.error_type),errorNote,e.session_id&&('会话 '+e.session_id),
        e.part_seq&&('第 '+e.part_seq+'/'+e.part_count+' 句'),e.blocker_id&&('阻塞任务 '+e.blocker_id),
        e.delivery_id&&('发件 '+e.delivery_id),e.progress_available===false&&'接口未提供工具过程事件'].filter(Boolean);
      return `<li class="${failed?'error':['ok','sent'].includes(e.status)?'ok':''}"><time>${e.ts?esc(full(e.ts)):'—'}</time><b>${esc(FLOW_STAGE_LABELS[e.stage]||e.stage)}</b>
        <span class="sbadge ${failed?'sb-error':(e.status==='ok'||e.status==='sent'?'sb-ok':'sb-manual')}">${esc(FLOW_STATUS_LABELS[e.status]||e.status)}</span>
        ${bits.length?`<div class="flow-meta">${esc(bits.join(' · '))}</div>`:''}${e.detail?`<div class="monitor-note ${failed?'warn':''}">${esc(e.detail)}</div>`:''}</li>`;
    }).join('');
    return `<details data-detail="flow:${esc(f.id)}" class="flow-card ${bad?'error':''}"><summary><div class="flow-summary"><b>${esc(f.contact)}</b><time>${esc(full(f.at))}</time>${queueBadge(f.state)}<span class="flow-meta">${esc(FLOW_STAGE_LABELS[currentFlowStage(f.events||[])]||'等待后续处理')}</span></div><div class="flow-preview">${esc(f.preview)}</div>
      ${bad?`<div class="warn">${esc(reason.error||reason.message||'需要人工核对')}</div>`:''}</summary>
      <div class="flow-body"><div class="flow-meta">${f.message_count||1} 条收件</div>
      <div class="monitor-note ${bad?'warn':''}">${esc(reason.message||'')}${reason.record_id?' · 任务 '+esc(reason.record_id):''}${reason.error?'<br>'+esc(reason.error):''}</div>
      <ol class="flow-list">${events}</ol><details class="diagnostic" data-detail="raw:${esc(f.id)}"><summary>诊断详情 · 请求 ID 与原始事件</summary>
      <div class="monitor-source">收件序号 ${esc((f.inbox_ids||[]).join(', '))} · 请求 ID：<code>${esc(f.request_id||'尚未合并/提交')}</code></div><pre class="pre">${esc(JSON.stringify(f.events||[],null,2))}</pre></details></div></details>`;
  }).join('');
  return `<div class="head"><h2>消息流转记录 · ${esc(state.wUid==='all'?'全部会话':state.wUid)}</h2>
    <div class="monitor-note">从 wxbot 收件入库开始显示。按用户和请求 ID 关联；未记录的阶段不会推断为成功。旧任务没有过程日志时显示“未确认”。</div>
    <div class="flow-meta">共 ${data.total||0} 轮 / 待合并消息 · 查询 ${esc(full(data.at))} · 每页 ${data.limit||50} 条</div>
    <details data-detail="flow-sources" class="diagnostic"><summary>诊断详情 · 数据来源</summary>${(data.sources||[]).map(s=>`<div class="monitor-source">${esc(s.path)} · ${esc(s.status)}${s.truncated?' · 仅读取最近 4MB':''}</div>`).join('')}</details></div>`+
    (cards||'<div class="monitor-note">当前没有消息流转记录</div>')+
    `<div class="row"><button id="w-flow-prev" ${data.offset>0?'':'disabled'}>上一页流转</button><span class="flow-meta">第 ${Math.floor((data.offset||0)/(data.limit||50))+1} 页</span><button id="w-flow-next" ${data.has_more?'':'disabled'}>下一页流转</button></div>`;
}

function renderWxPane(){
  const d = state.wdata;
  if(!d){ $('#pane').innerHTML='<div class="empty">载入中…</div>'; return; }
  let evs = d.events.filter(e=>(state.wUid==='all' || e.uid===state.wUid)&&matchesQuery(e.uid,e.content,e.direction));
  if(state.wKind==='chat') evs = evs.filter(e=>e.direction==='received'||e.direction==='reply');
  else if(state.wKind==='outbound') evs = evs.filter(e=>e.direction==='outbound');
  else if(state.wKind==='slow') evs = evs.filter(e=>e.elapsed_s!=null && e.elapsed_s>300);
  if(state.wOrder==='asc') evs = evs.slice().reverse();
  const st = d.stats;
  const head = `<div class="head">
    <h2>wxbot 通道 · 真实聊天窗口流水
      </h2>
    <div class="kv">
      <span>事件 <b>${st.events}</b></span>
      <span>收到 <b>${st.received}</b></span>
      <span>回复 <b>${st.reply}</b></span>
      <span>外发 <b>${st.outbound}</b></span>
      <span>超时 <b class="${st.timeouts?'slow':''}">${st.timeouts}</b></span>
      <span>慢轮(&gt;300s) <b class="${st.slow_rounds?'slow':''}">${st.slow_rounds}</b></span>
      <span>任务推断 <b>${st.inferred_tasks}</b></span>
      <span>会话 <b>${st.sessions}</b></span>
      <span style="flex:1"></span>
      <span class="k">生成 ${esc(d.generated_at)}</span>
    </div></div>`;
  const flowHtml=['all','chat','flow'].includes(state.wKind)?renderMessageFlow(d.flow):'';
  if(state.wKind==='flow') evs=[];
  let lastDay = null, html = '';
  for(const e of evs){
    const day = daystr(e.time);
    if(day!==lastDay){ html += `<div class="day"><b>${day}</b></div>`; lastDay = day; }
    html += wxEvent(e);
  }
  $('#pane').innerHTML = flowHtml + (state.wKind==='flow'?'':head+(html?`<details data-detail="chat-history" ${flowHtml?'':'open'}><summary>历史聊天流水（按时间关联）</summary>${html}</details>`:(!flowHtml?'<div class="empty">没有匹配的事件</div>':'')));
  if(flowHtml){
    const prev=$('#w-flow-prev'),next=$('#w-flow-next');
    if(prev) prev.onclick=()=>{state.wFlowOffset=Math.max(0,state.wFlowOffset-50);loadWxbot();};
    if(next) next.onclick=()=>{state.wFlowOffset+=50;loadWxbot();};
  }
}
