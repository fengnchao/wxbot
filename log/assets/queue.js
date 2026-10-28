const QUEUE_LABELS={review:'结果待核对（不阻塞）',restart_discard:'重启停止续发',draft_hold:'草稿待人工处理',unbatched:'待合并',ready:'待提交模型',processing:'等待模型',waiting_delivery:'回复就绪',
  pending:'待发送',sending:'键入中',confirming:'发送确认中',blocked:'已阻断',uncertain:'结果不确定',
  sent:'已发送',skipped:'已跳过',timeout_discard:'超时丢弃',done:'整轮完成',idle:'空闲',pending_capture:'待采集',merging:'合并中',ready_to_merge:'待调度',state_mismatch:'状态待核对',
  completed:'已完成',ok:'完成',failed:'失败',error:'错误',started:'已开始',running:'执行中',accepted:'已接受',finished:'已结束'};
const ORIGIN_LABELS={file:'文件值',default:'默认值',code:'固定规则',runtime:'运行参数'};
function queueBadge(status){
  const cls=['blocked','uncertain','failed','error','model_failed','rejected','not_submitted','media_failed'].includes(status)?'sb-error':(['done','sent','skipped','completed','ok','finished'].includes(status)?'sb-ok':'sb-manual');
  return `<span class="sbadge ${cls}">${esc(QUEUE_LABELS[status]||status)}</span>`;
}
QUEUE_LABELS.model_failed='模型失败已结束';
Object.assign(QUEUE_LABELS,{batched:'已合并',received:'Butler 已收件',rejected:'已拒绝',not_submitted:'未提交',cancelled:'已取消',partial_deleted:'部分已发，其余已删除'});
Object.assign(QUEUE_LABELS,{preparing:'图片准备中',media_failed:'图片准备失败',awaiting_bot:'等待机器人收件'});
function modelRecoveryNote(row){
  const retry=row.retry_at!=null?`下次自动重试：${full(row.retry_at)} · 已尝试 ${row.attempts||0}/${row.max_attempts||3} 次`:
    row.retry_safe===false?'结果未知，不自动重放本条；到期结束失败批次并放行后续消息':'';
  return retry?`<div class="monitor-note">${esc(retry)}</div>`:'';
}
async function loadQueue(){
  if(state.qBusy) return;
  const request=++state.qRequest;
  const qs=new URLSearchParams({contact:state.qContact,state:state.qState,scope:state.qScope,limit:'50',
    ...Object.fromEntries(Object.entries(state.qOffsets).map(([k,v])=>[k+'_offset',String(v)]))});
  try{
    const data=await apiGet('/api/queue?'+qs);
    if(request!==state.qRequest||state.tab!=='queue') return;
    state.qdata=data; state.qError='';
  }catch(e){
    if(request!==state.qRequest||state.tab!=='queue') return;
    state.qdata=null; state.qError=e.message||'队列载入失败';
  }
  try{renderQueueNav(); renderQueuePane();}
  catch(error){state.qError='队列展示失败：'+error.message;$('#pane').innerHTML=`<div class="empty warn">${esc(state.qError)}。请刷新页面加载最新脚本。</div>`;}
}
function renderQueueNav(){
  const contacts=state.qdata?.contacts||[];
  $('#list').innerHTML=`<div class="user ${!state.qContact?'sel':''}" data-qindex="-1"><div class="nm">全部会话</div><div class="st">查看所有用户和群聊的队列</div></div>`+
    contacts.map((c,i)=>`<div class="user ${state.qContact===c.contact?'sel':''}" data-qindex="${i}">
      <div class="nm">${esc(c.contact)} ${queueBadge(c.reason.code)}</div>
      <div class="st">待合并 <b>${c.unbatched}</b> · 待发 <b>${Object.entries(c.outbox).filter(([s])=>!['sent','skipped'].includes(s)).reduce((n,[s,v])=>n+v,0)}</b></div>
      <div class="pv">${esc(c.reason.message)}</div></div>`).join('');
  $('#list').querySelectorAll('[data-qindex]').forEach(el=>el.onclick=()=>{
    const i=Number(el.dataset.qindex); state.qContact=i<0?'':contacts[i].contact; resetQueuePages(); loadQueue();
  });
}
const QUEUE_ACTION_LABELS={retry:'重试',sent:'确认已发',skip:'立即丢弃'};
function queueActionButtons(r,kind,records){
  if(!state.qdata?.actions_enabled || !r.actions?.length) return '';
  const index=records.push({id:r.id||r.record_id,kind,contact:r.contact,
    expected_state:r.state,expected_finished_at:r.finished_at??null,
    ...(kind==='batches'?{expected_attempts:r.attempts}:{})})-1;
  return `<div class="queue-actions">${r.actions.map(action=>`<button class="${action==='skip'?'discard':''}" data-q-action="${action}" data-q-record="${index}" ${state.qBusy?'disabled':''}>${QUEUE_ACTION_LABELS[action]||''}</button>`).join('')}</div>`;
}
function queueCountdown(at){
  if(at==null) return '';
  const left=Math.max(0,Math.ceil(at-Date.now()/1000));
  return `<div class="monitor-note warn" data-discard-at="${Number(at)}">${left?'剩余 '+left+' 秒自动丢弃':'已到丢弃时间，等待 wxbot 巡检'}</div>`;
}
function updateQueueCountdowns(){
  if(state.tab!=='queue') return;
  $('#pane').querySelectorAll('[data-discard-at]').forEach(el=>{
    const left=Math.max(0,Math.ceil(Number(el.dataset.discardAt)-Date.now()/1000));
    el.textContent=left?'剩余 '+left+' 秒结束失败任务':'已到结束时间，等待 wxbot 巡检';
  });
}
setInterval(updateQueueCountdowns,1000);
async function performQueueAction(record,action){
  if(state.qBusy || !record || !QUEUE_ACTION_LABELS[action]) return;
  const caution=action==='retry'?(record.kind==='outbox'?
    '请先核对微信实际发送结果，并清理残留草稿。重试可能重复发送，仍在处理的整轮失败期限不会重置；已退出调度的任务明确重试后开启新期限，只重试所选块。':
    '请先核对模型与工具实际执行结果。重试可能重复执行工具。'):
    action==='sent'?'请确认已在微信看到这条消息实际发送成功。此操作只登记结果，不再发送。':
    '此操作放弃这条任务并释放后续队列，保留消息和失败记录。';
  if(!confirm(`${QUEUE_ACTION_LABELS[action]} · ${record.contact}\n任务 ${record.id}\n\n${caution}`)) return;
  state.qBusy=true;state.qMessage='正在处理…';state.qActionFailed=false;
  if(state.tab==='queue')renderQueuePane();
  try{
    const response=await fetch('/api/queue-action',{method:'POST',
      headers:{'Content-Type':'application/json','X-Wxbot-Queue-Action':'1'},
      body:JSON.stringify({...record,action,acknowledge:true})});
    const data=await response.json();
    if(!response.ok||!data.ok)throw new Error(data.error||'操作失败');
    state.qMessage=`${record.contact} · ${record.id}：${QUEUE_ACTION_LABELS[action]}已登记`;
  }catch(error){state.qActionFailed=true;state.qMessage=error.message||'操作失败';}
  finally{state.qBusy=false;}
  if(state.tab==='queue')await loadQueue();
}
async function performQueueDeleteUnsent(){
  if(state.qBusy) return;
  if(!confirm('删除所有未发送成功消息\n\n范围：微信和 Telegram 的全部会话，不受当前筛选或分页影响。\n删除消息记录并停止后续投递；已发送成功的记录保留。\n正在输入、确认发送结果或提交中的任务本次保留，请稍后处理。\n尚未实际采集的微信会话继续接收，本次保留。\n微信输入框已有草稿需自行清理。')) return;
  state.qBusy=true;state.qMessage='正在删除…';state.qActionFailed=false;
  if(state.tab==='queue')renderQueuePane();
  try{
    const response=await fetch('/api/queue-delete-unsent',{method:'POST',
      headers:{'Content-Type':'application/json','X-Wxbot-Queue-Action':'1'},
      body:JSON.stringify({acknowledge:true})});
    const data=await response.json();
    if(!response.ok||!data.ok)throw new Error(data.error||'删除失败');
    const wx=data.wxbot||{},telegram=data.telegram||{};
    const protectedActive=(wx.protected_active||0)+(telegram.protected_active||0);
    state.qMessage=`已删除：微信 ${wx.deleted_messages||0} 条消息、${wx.deleted_deliveries||0} 条投递；Telegram ${telegram.deleted_messages||0} 条消息、${telegram.deleted_deliveries||0} 条投递。本次保留正在处理的任务 ${protectedActive} 个（微信 ${wx.protected_active||0}，Telegram ${telegram.protected_active||0}）${protectedActive?'，请稍后处理。':'。'}`;
    if(wx.drafts_to_clear)state.qMessage+=`另有 ${wx.drafts_to_clear} 个会话的微信输入框草稿需自行清理。`;
    if(wx.protected_reads)state.qMessage+=`保留任务中有 ${wx.protected_reads} 个尚未采集的微信会话。`;
  }catch(error){state.qActionFailed=true;state.qMessage=error.message||'删除失败';}
  finally{state.qBusy=false;}
  if(state.tab==='queue')await loadQueue();
}
function queueReason(c,records){
  const r=c.reason, bad=['blocked','uncertain'].includes(r.code);
  const visibleRows=r.record_kind==='outbox'?
    (state.qdata?.rounds||[]).filter(row=>matchesQuery(row.contact,row.preview,row.error,row.id)).flatMap(row=>row.parts||[]):
    (state.qdata?.[r.record_kind]||[]).filter(row=>matchesQuery(row.contact,row.preview,row.error,row.id));
  const actionsInList=visibleRows.some(row=>String(row.id)===String(r.record_id)&&row.actions?.length);
  const labels={sent:'已核对实际发送成功',retry:'确需重试（可能重复操作）',skip:'放弃此异常任务'};
  return `<div class="queue-reason ${bad?'error':''}"><h3>${esc(c.contact)} · ${queueBadge(r.code)}</h3>
    <div>${esc(r.message)}${r.wait_seconds>0?' · 约 '+Math.ceil(r.wait_seconds)+' 秒':''}</div>
    ${r.record_id?`<div class="monitor-source">${r.record_kind==='outbox'?'发件 ID':'批次 ID'}：<code>${esc(r.record_id)}</code></div>`:''}
    ${r.error?`<div class="monitor-note warn">${esc(r.error)}</div>`:''}
    ${modelRecoveryNote(r)}
    ${queueCountdown(r.discard_at)}
    ${r.actions?.length?'<div class="monitor-source">人工核对：先确认微信实际发送结果及输入框草稿，再操作。</div>':''}
    ${actionsInList?'<div class="monitor-note">在下方对应任务行执行人工核对操作。</div>':queueActionButtons({...r,contact:c.contact},r.record_kind,records)}
    ${r.commands?`<details><summary>查看对应恢复命令</summary><div class="monitor-note">先核对微信、草稿和实际发送结果；也可使用页面的人工核对按钮。以下命令请在项目目录的 PowerShell 中使用，不会自动执行。</div>
      <div class="queue-commands">${Object.entries(r.commands).map(([kind,cmd])=>`<div>${esc(labels[kind]||kind)}<code>${esc(cmd)}</code></div>`).join('')}</div></details>`:''}</div>`;
}
function resetQueuePages(){state.qOffset=0;state.qOffsets={inbox:0,batches:0,outbox:0,rounds:0,telegram:0};}
function telegramQueueTable(data){
  if(!data)return '<div class="monitor-note warn">Telegram 队列接口尚未加载，请手动重启 log。</div>';
  if(data.status!=='ok')return `<div class="monitor-note ${data.status==='error'?'warn':''}">Telegram：${esc(data.error)}</div>`;
  const page=data.page,rows=data.rows.filter(r=>matchesQuery(r.contact,r.uid,r.id,r.preview,r.reason,r.error,r.targets));
  return `<h3 class="monitor-section-title">Telegram 收件 / 新闻转发 · ${page.total} 条</h3>
    <div class="monitor-note">按发送者数字 ID 区分用户；收件成功与微信发送成功分别记录。阻塞分段显示前置任务，跨系统未有关联证据时不合并为同一条。</div>`+
    (rows.length?`<div class="monitor-table-wrap"><table class="monitor-table"><thead><tr><th>用户 / 状态</th><th>内容 / 阻塞原因</th><th>时间 / 去向</th></tr></thead><tbody>${rows.map(r=>`<tr>
      <td>${esc(r.contact)}<br>${queueBadge(r.state)}<div class="monitor-source">${esc(r.id)}</div></td>
      <td class="preview">${esc(r.preview)}${r.has_media?'<div class="monitor-note">含媒体附件</div>':''}<div class="monitor-note ${r.error?'warn':''}">${esc(r.error||r.reason)}</div>
      <details data-detail="telegram:${esc(r.id)}" ${r.error?'open':''}><summary>逐人发送与阻塞详情 · ${r.deliveries.length} 段</summary>
      ${r.deliveries.map(t=>`<div class="queue-reason ${['uncertain','blocked','not_submitted','rejected'].includes(t.state)?'error':''}"><b>${esc(t.contact)} · 第 ${t.part} 段</b> ${queueBadge(t.state)}<div>${esc(t.reason)}</div><div class="monitor-source">任务 ${esc(t.id)}${t.blocker_id?' · 阻塞任务 '+esc(t.blocker_id):''} · ${esc(full(t.updated))}</div></div>`).join('')||'<div class="monitor-note">尚无新闻投递任务，请查看上面的原因。</div>'}
      ${r.deliveries_truncated?'<div class="warn">仅显示前 200 个分段，完整记录保存在接收器数据库。</div>':''}</details></td>
      <td>消息 ${esc(full(r.created_at))}<br>Butler 入库 ${esc(full(r.received_at))}<div>${esc(r.targets||'尚未分配接收人')}</div></td></tr>`).join('')}</tbody></table></div>`:
      '<div class="monitor-note">当前筛选下没有 Telegram 消息</div>')+
    `<div class="pagination"><button data-tg-page="-1" ${page.offset?'':'disabled'}>上一页</button><span>第 ${Math.floor(page.offset/page.limit)+1} 页 · 共 ${page.total} 条</span><button data-tg-page="1" ${page.has_more?'':'disabled'}>下一页</button></div>`;
}
function queueTable(title,rows,kind,page,records){
  rows=rows.filter(r=>matchesQuery(r.contact,r.preview,r.error,r.id));
  const offset=page?.offset||0,limit=page?.limit||50;
  const pager=`<div class="pagination"><button data-q-page="${kind}" data-q-delta="-1" ${offset?'':'disabled'}>上一页</button><span>第 ${Math.floor(offset/limit)+1} 页 · 共 ${page?.total||0} 条</span><button data-q-page="${kind}" data-q-delta="1" ${page?.has_more?'':'disabled'}>下一页</button></div>`;
  return `<h3 class="monitor-section-title">${title} <span class="monitor-source">${page?.total||0} 条，当前显示 ${rows.length} 条</span></h3>`+
    (rows.length?`<div class="monitor-table-wrap"><table class="monitor-table"><thead><tr><th>会话 / 状态</th><th>内容预览</th><th>时间 / 进度</th><th>任务 ID</th></tr></thead><tbody>`+
    rows.map(r=>`<tr><td>${esc(r.contact)}<br>${queueBadge(r.display_state||(r.resolution==='timeout'?'timeout_discard':r.state))}</td><td class="preview">${esc(r.preview)}<div class="monitor-source">${r.characters} 字${r.characters>240?'，仅显示前 240 字':''}</div>
      ${r.error?`<div class="warn">${esc(r.error)}</div>`:''}${queueCountdown(r.discard_at)}
      ${kind==='batches'?modelRecoveryNote(r):''}
      ${queueActionButtons(r,kind,records)}</td><td>${esc(full(r.received_at??r.created_at))}
      ${kind==='outbox'?`<div>第 ${r.part_seq}/${r.part_count} 块</div>`:kind==='batches'?`<div>已发 ${r.sent_parts}/${r.part_count} 块</div><div>提交次数 ${r.attempts||0}</div>`:''}
      ${r.started_at?`<div class="monitor-source">模型开始 ${esc(full(r.started_at))}</div>`:''}
      ${r.submitted_at?`<div class="monitor-source">回车 ${esc(full(r.submitted_at))}</div>`:''}</td>
      <td><details data-detail="queue:${kind}:${esc(r.id)}"><summary>任务详情</summary><code>${esc(r.id)}</code>${r.batch_id?`<div class="monitor-source">批次 ${esc(r.batch_id)}</div>`:''}</details></td></tr>`).join('')+
      '</tbody></table></div>':'<div class="monitor-note">当前筛选下没有任务</div>')+pager;
}
function replyRoundsTable(rounds,page,records){
  const rows=(rounds||[]).filter(r=>matchesQuery(r.contact,r.preview,r.error,r.id));
  return '<h3 class="monitor-section-title">回复整轮 / 主动推送</h3>'+rows.map(r=>
    `<div class="queue-reason"><h3>${esc(r.contact)} · ${queueBadge(r.display_state||r.state)}</h3>
      <div>${esc(r.preview)}</div><div class="monitor-note">已发 ${r.sent_parts} / ${r.part_count} 块 · ${esc(full(r.created_at))}</div>
      ${r.error?`<div class="warn">${esc(r.error)}</div>`:''}${queueCountdown(r.discard_at)}
      ${r.parts.filter(p=>p.actions?.length).map(p=>`<div class="queue-actions">第 ${p.part_seq} 块 ${queueActionButtons(p,'outbox',records)}</div>`).join('')}
      <details data-detail="reply-round:${esc(r.id)}"><summary>展开本轮分块与诊断</summary>
      ${r.parts.map(p=>`<div class="monitor-note"><b>第 ${p.part_seq} 块</b> ${queueBadge(p.display_state||p.state)} · ${p.characters} 字
        <div>${esc(p.preview)}</div><div class="warn">${esc(p.error||'')}</div><code>${esc(p.id)}</code></div>`).join('')}</details></div>`).join('')+
    (rows.length?'':'<div class="monitor-note">当前筛选下没有回复任务</div>')+
    `<div class="pagination"><button data-q-page="rounds" data-q-delta="-1" ${page?.offset?'':'disabled'}>上一页</button>
     <span>第 ${Math.floor((page?.offset||0)/(page?.limit||50))+1} 页 · 共 ${page?.total||0} 轮</span>
     <button data-q-page="rounds" data-q-delta="1" ${page?.has_more?'':'disabled'}>下一页</button></div>`;
}
function queueEventTable(events){
  const labels={restart_discard:'重启停止续发',review:'结果待核对，停止本轮续发',timeout:'整轮失败超时结束',failed:'发送失败',timeout_discard:'失败超时丢弃',retry:'人工重试',confirm_sent:'人工确认已发',manual_discard:'人工丢弃',
    model_retryable:'模型失败，等待自动重试',model_uncertain:'模型结果未知',model_retry:'模型自动重试',model_abandoned:'模型失败已结束'};
  return '<h3 class="monitor-section-title">失败与恢复记录 · 最近50条</h3>'+(events.length?
    `<div class="monitor-table-wrap"><table class="monitor-table"><thead><tr><th>时间 / 会话</th><th>处理记录</th><th>任务</th></tr></thead><tbody>${events.map(e=>
      `<tr><td>${esc(full(e.at))}<br>${esc(e.contact)}</td><td><b>${esc(labels[e.action]||e.action)}</b><div class="monitor-note">${esc(e.reason)}</div>
      ${Object.keys(e.details||{}).length?`<details data-detail="failure:${esc(e.seq||e.record_id+':'+e.at)}"><summary>失败现场信息</summary><pre>${esc(JSON.stringify(e.details,null,2))}</pre></details>`:''}</td>
      <td><code>${esc(e.record_id)}</code><div class="monitor-source">来源 ${esc(e.source)}</div></td></tr>`).join('')}</tbody></table></div>`:
    '<div class="monitor-note">暂无失败或人工处理记录</div>');
}
function renderQueuePane(){
  const d=state.qdata;
  const deletionControls=`<div class="queue-actions"><button id="q-delete-unsent" class="discard" ${state.qBusy?'disabled':''}>删除所有未发送成功消息</button></div><div class="monitor-note">适用于全部微信与 Telegram 会话，不受当前筛选或分页影响。</div>`;
  const feedback=state.qMessage?`<div class="monitor-note ${state.qActionFailed?'warn':''}">${esc(state.qMessage)}</div>`:'';
  if(!d){
    $('#pane').innerHTML=`<div class="head"><h2>收发队列</h2>${deletionControls}${feedback}</div><div class="empty warn">${esc(state.qError||'正在载入队列…')}</div>`;
    $('#q-delete-unsent').onclick=performQueueDeleteUnsent;
    return;
  }
  d.counts??={};d.pages??={};
  const total=(which,status)=>d.counts[which]?.[status]||0;
  const contacts=(d.contacts||[]).filter(c=>(state.qContact?c.contact===state.qContact:c.reason.code!=='idle')&&matchesQuery(c.contact,c.reason.message,c.reason.error));
  const records=[];
  const configuredTimeout=Number(d.failure_timeout_seconds);
  const timeoutSeconds=Number.isFinite(configuredTimeout)&&configuredTimeout>0?configuredTimeout:180;
  $('#pane').innerHTML=`<div class="head"><h2>收发队列 · ${esc(state.qContact||'全部会话')}</h2>
    ${deletionControls}
    ${d.status!=='ok'?`<div class="warn">wxbot 队列：${esc(d.error)} · ${esc(d.database)}</div>`:''}
    <div class="monitor-grid"><span class="chip">Telegram <b>${Object.values(d.telegram?.counts||{}).reduce((n,v)=>n+v,0)}</b></span><span class="chip">全队列待合并 <b>${d.counts.unbatched||0}</b></span><span class="chip">待提交 <b>${total('batches','ready')}</b></span>
    <span class="chip">等待模型 <b>${total('batches','processing')}</b></span><span class="chip">待发块 <b>${total('outbox','pending')}</b></span>
    <span class="chip">异常块 <b class="warn">${total('outbox','blocked')+total('outbox','uncertain')}</b></span></div>
    <div class="monitor-note">同一会话按顺序处理。发件失败从首次失败起最多等待${timeoutSeconds}秒，超时结束本轮剩余分块并保留日志；结果不确定的保留核对记录且不阻塞后续消息。模型确认未提交时最多尝试3次；模型结果未知时不重放，失败满${timeoutSeconds}秒结束旧批次，继续处理后续消息。人工核对按钮在下方异常任务旁，操作前需要确认。</div>
    ${feedback}
    <details class="diagnostic" data-detail="queue-settings"><summary>诊断详情 · 队列规则与来源</summary><div class="monitor-source">倒计时按配置文件计算，修改后需重启 wxbot；运行参数未核验。</div>
    ${!d.actions_enabled?'<div class="monitor-note warn">请先重启更新后的 wxbot 完成队列升级，启用失败超时规则和人工核对按钮。</div>':''}
    <div class="monitor-source">数据库：${esc(d.database)} · 查询时间：${esc(full(d.at))}</div></details></div>`+
    `<div class="segmented">${[['all','全部消息'],['active','待处理'],['issues','异常待核对'],['history','历史记录']].map(([value,label])=>`<button data-q-scope="${value}" class="${state.qScope===value?'on':''}">${label}</button>`).join('')}<button id="q-clear-filters">清除全部筛选</button></div>
    <div class="monitor-note">${['all','history'].includes(state.qScope)?'最新记录在前':state.qScope==='issues'?'最早任务在前 · 请先核对实际发送结果':'按实际处理序号排列'} · 状态：${esc(state.qState==='all'?'全部':QUEUE_LABELS[state.qState]||state.qState)}${currentQuery()?' · 搜索作用于本页及当前会话摘要':''}</div>`+
    (state.qScope!=='history'?(contacts.length?contacts.map(c=>queueReason(c,records)).join(''):'<div class="monitor-note">没有待处理任务</div>'):'')+
    telegramQueueTable(d.telegram)+
    (['all','active'].includes(state.qScope)?queueTable(state.qScope==='all'?'微信收件（含已合并）':'待合并消息',d.inbox||[],'inbox',d.pages.inbox,records):'')+queueTable('模型批次',d.batches||[],'batches',d.pages.batches,records)+
    replyRoundsTable(d.rounds,d.pages.rounds,records)+
    `<details data-detail="queue-audit" ${state.qScope==='issues'?'open':''}><summary>失败、自动恢复与人工核对记录</summary>${queueEventTable(d.events||[])}</details>`;
  $('#q-delete-unsent').onclick=performQueueDeleteUnsent;
  $('#pane').querySelectorAll('[data-q-scope]').forEach(button=>button.onclick=()=>{
    state.qScope=button.dataset.qScope;state.qState='all';$('#q-state').value='all';resetQueuePages();loadQueue();
  });
  $('#q-clear-filters').onclick=()=>{state.qContact='';state.qState='all';state.qScope='all';state.viewSearch.queue='';$('#view-search').value='';$('#q-state').value='all';resetQueuePages();loadQueue();};
  $('#pane').querySelectorAll('[data-tg-page]').forEach(button=>button.onclick=()=>{
    const page=d.telegram.page;state.qOffsets.telegram=Math.max(0,page.offset+Number(button.dataset.tgPage)*page.limit);loadQueue();
  });
  $('#pane').querySelectorAll('[data-q-page]').forEach(button=>button.onclick=()=>{
    const kind=button.dataset.qPage,page=d.pages[kind];state.qOffsets[kind]=Math.max(0,(page?.offset||0)+Number(button.dataset.qDelta)*(page?.limit||50));loadQueue();
  });
  $('#pane').querySelectorAll('[data-q-action]').forEach(button=>button.onclick=()=>
    performQueueAction(records[Number(button.dataset.qRecord)],button.dataset.qAction));
}
