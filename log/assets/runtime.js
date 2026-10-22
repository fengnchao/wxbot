async function loadRuntime(){
  const request=++state.rRequest;
  try{
    const data=await apiGet('/api/runtime');
    if(state.tab!=='runtime'||request!==state.rRequest)return;
    state.runtime=data;renderRuntime();
  }catch(error){if(state.tab==='runtime'&&request===state.rRequest)$('#pane').innerHTML=`<div class="empty warn">${esc(error.message||error)}</div>`;}
}
function renderRuntime(){
  const data=state.runtime;if(!data)return;
  const contacts=[...new Set([...(data.memory||[]),...(data.events||[])].map(x=>x.contact).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
  $('#list').innerHTML=`<div class="user ${!state.rContact?'sel':''}" data-r-contact=""><div class="nm">全部会话</div><div class="st">${esc(data.backend||'未知')} · 协议 ${esc(data.protocol_version||'-')}</div></div>`+
    contacts.map(name=>`<div class="user ${state.rContact===name?'sel':''}" data-r-contact="${esc(name)}"><div class="nm">${esc(name)}</div></div>`).join('');
  const table=(headers,rows)=>`<div class="monitor-table-wrap"><table class="monitor-table"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join('')||`<tr><td colspan="${headers.length}">暂无匹配记录</td></tr>`}</tbody></table></div>`;
  const labels={model_request:'请求模型',model_tool:'调用工具',model_result:'模型结果',model_session:'会话恢复',reminder_delivery:'提醒投递'};
  const memory=(data.memory||[]).filter(x=>(!state.rContact||state.rContact===x.contact)&&matchesQuery(x.contact,x.key,x.value));
  const events=(data.events||[]).filter(x=>(!state.rContact||state.rContact===x.contact)&&(!state.rStatus||state.rStatus===x.status)&&matchesQuery(x.contact,x.stage,x.status,JSON.stringify(x.details)));
  const statuses=[...new Set((data.events||[]).map(x=>x.status).filter(Boolean))];
  $('#pane').innerHTML=`<div class="head"><h2>模型与记忆</h2><div class="kv"><span>当前后端 <b>${esc(data.backend)}</b></span><span>协议 ${esc(data.protocol_version)}</span></div><div class="monitor-note">按最近更新时间展示。当前接口最多读取 100 条记忆、100 条运行事件；筛选作用于已读取记录。</div><button id="r-jobs">查看定时任务与提醒</button></div>
    <h3 class="monitor-section-title">用户记忆 · ${memory.length} 条</h3>${table(['会话 / 条目','内容','更新时间'],memory.map(x=>[esc(x.contact||'未命名')+'<br><code>'+esc(x.key)+'</code>',longText(x.value,100,`memory:${x.contact}:${x.key}:${x.updated}`),esc(full(x.updated))]))}
    <div class="row"><h3 class="monitor-section-title">运行记录 · ${events.length} 条</h3><select id="r-status" aria-label="运行状态筛选"><option value="">全部状态</option>${statuses.map(s=>`<option value="${esc(s)}" ${state.rStatus===s?'selected':''}>${esc(s)}</option>`).join('')}</select></div>
    ${table(['时间 / 会话','阶段 / 状态','信息'],events.map(x=>[esc(full(x.at))+'<br>'+esc(x.contact),esc(labels[x.stage]||x.stage)+'<br>'+queueBadge(x.status),longText(typeof x.details==='string'?x.details:JSON.stringify(x.details,null,2),100,`event:${x.id||x.at+':'+x.contact+':'+x.stage}`)]))}`;
  $('#r-jobs').onclick=()=>switchTab('jobs');
  $('#r-status').onchange=()=>{state.rStatus=$('#r-status').value;renderRuntime();};
  $('#list').querySelectorAll('[data-r-contact]').forEach(el=>el.onclick=()=>{state.rContact=el.dataset.rContact;renderRuntime();});
}
