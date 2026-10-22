async function apiGet(u){
  const r = await fetch(u), data = await r.json();
  if(!r.ok) throw new Error((data && (data.detail||data.error)) || `HTTP ${r.status}`);
  markRefreshed();
  return data;
}

async function loadHeartbeat(){
  state.hError = '';
  try{
    state.hdata = await apiGet('/api/heartbeat-config');
    try{
      state.hstatus = await apiGet('/api/heartbeat-status?limit=30');
      state.hStatusError = '';
    }catch(e){ state.hstatus = null; state.hStatusError = e.message||String(e); }
    const contacts = state.hdata.contacts || [];
    if(!contacts.some(c=>c.name===state.hContact)) state.hContact = contacts[0]?.name || '';
    if(state.hContact) await loadHeartbeatSkills(state.hContact);
    else if(!state.hContact){ state.hSkills=[]; state.hDraft=null; }
  }catch(e){ state.hError = '载入失败：'+(e.message||e); }
  if(state.tab!=='heartbeat') return;
  renderHeartbeatNav();
  renderHeartbeatPane();
}

function isRoleSkill(skill){
  return (Array.isArray(skill.tags) ? skill.tags : [])
    .some(tag=>String(tag).trim().toLowerCase()==='butler-role');
}

async function loadHeartbeatSkills(contact){
  if(state.hDraft&&state.hSkillsContact)state.hDrafts.set(state.hSkillsContact,{...state.hDraft,allowed_skills:[...state.hDraft.allowed_skills]});
  state.hDraft=null;
  const requestId=++state.hRequest;
  state.hContact = contact;
  state.hSkillsContact = contact;
  state.hSkills = [];
  state.hError = '';
  state.hSaved = '';
  try{
    const data = await apiGet('/api/skills?contact='+encodeURIComponent(contact));
    if(requestId!==state.hRequest) return;
    state.hSkills = data.skills || [];
    const saved = (state.hdata && state.hdata.policies && state.hdata.policies[contact]) || {};
    const roleOptions = new Set(state.hSkills.filter(isRoleSkill).map(s=>s.name));
    const toolOptions = new Set(state.hSkills.filter(s=>!isRoleSkill(s)).map(s=>s.name));
    const savedRole = saved.role_skill || '';
    const role = roleOptions.has(savedRole) ? savedRole : '';
    const allowed = Array.isArray(saved.allowed_skills)
      ? [...new Set(saved.allowed_skills.filter(name=>toolOptions.has(name)))] : [];
    state.hDraft = state.hDrafts.get(contact)||{role_skill:role, allowed_skills:allowed,
                    heartbeat_enabled:saved.heartbeat_enabled===true};
    if(savedRole && !role) state.hError='已保存的角色 skill 未标记 butler-role，请重新选择角色 skill。';
  }catch(e){ if(requestId!==state.hRequest) return; state.hError = '技能目录载入失败：'+(e.message||e); }
  renderHeartbeatNav();
  renderHeartbeatPane();
}

function renderHeartbeatNav(){
  if(state.tab!=='heartbeat') return;
  const el = $('#list'), contacts = ((state.hdata && state.hdata.contacts) || []).slice().sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'));
  el.innerHTML = contacts.length ? contacts.map(c=>{
    const p = (state.hdata.policies||{})[c.name] || {};
    return `<div class="user ${state.hContact===c.name?'sel':''}" data-hcontact="${esc(c.name)}">
      <div class="nm">${esc(c.label||c.name)} ${p.heartbeat_enabled?'<span class="tag">心跳开</span>':''}</div>
      <div class="uid">${esc(c.name)} · ${esc(c.profile)}</div>
      <div class="pv">${p.role_skill?'角色：'+esc(p.role_skill):'尚未绑定角色 skill'}</div>
    </div>`;
  }).join('') : '<div class="empty">Butler 配置中没有可管理的私聊联系人</div>';
  el.querySelectorAll('[data-hcontact]').forEach(n=>n.onclick=()=>loadHeartbeatSkills(n.dataset.hcontact));
}

function heartbeatDate(value){
  if(!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : full(date.getTime()/1000);
}

function heartbeatEventTitle(event){
  const labels={scheduler_started:'Butler 心跳调度启动',scheduled:'下次心跳已安排',
    trigger_started:'心跳开始执行',trigger_skipped:'本轮跳过',contact_selected:'选中联系人',
    hermes_call_started:'开始调用 模型运行时',hermes_result:'模型运行时 返回结果',
    push_succeeded:'建议已发送',push_failed:'建议发送失败',error:'执行错误',
    scheduler_not_started:'调度未启动',scheduler_stopping:'调度正在停止',scheduler_stopped:'调度已停止',
    manual_trigger_requested:'收到手动触发请求',manual_trigger_accepted:'Butler 已接受手动触发',
    manual_trigger_rejected:'手动触发未执行'};
  if(event.event==='hermes_result') return event.result==='none'?'模型运行时 检查完成：没有建议':
    (event.result==='suggestion'?'模型运行时 返回了建议':(event.result==='invalid'?'模型运行时 返回格式无效':'模型运行时 返回'));
  if(event.event==='error') return '执行错误（'+(event.phase||'未知阶段')+'）';
  return labels[event.event]||event.event||'心跳事件';
}

function renderHeartbeatStatus(){
  const status=state.hstatus;
  if(!status) return `<div class="hbstatus"><h2>心跳运行记录</h2><div class="warn">读取运行记录失败：${esc(state.hStatusError||'未知错误')}</div></div>`;
  const events=(Array.isArray(status.events)?status.events:[]).filter(e=>(!e.contact||e.contact===state.hContact)&&matchesQuery(e.contact,e.event,e.text,e.detail,e.role_skill));
  const due=Number(status.next_run_at);
  const next=Number.isFinite(due)&&due>0?full(due):'尚未安排';
  const rows=events.map(event=>{
    const meta=[event.source&&('来源：'+(event.source==='manual'?'手动':'定时')),
      event.contact&&('用户：'+event.contact),event.role_skill&&('角色：'+event.role_skill),
      event.elapsed_ms!=null&&('耗时：'+event.elapsed_ms+' ms'),
      Array.isArray(event.allowed_skills)&&event.allowed_skills.length&&('允许技能：'+event.allowed_skills.join('、'))]
      .filter(Boolean).join(' · ');
    const detail=event.text||event.detail||(event.next_run_at?'下次触发：'+full(Number(event.next_run_at)):
      ({no_enabled_contacts:'没有已开启心跳的联系人',contact_not_configured:'联系人未配置',
        policy_missing:'联系人尚未保存角色和 Skill 配置',policy_unavailable:'角色和 Skill 配置不可读取',
        busy:'已有一轮心跳正在执行',start_failed:'无法启动执行'}[event.reason]||''));
    return `<div class="hbevent"><div class="evt"><b>${esc(heartbeatEventTitle(event))}</b><time>${esc(heartbeatDate(event.at))}</time></div>
      ${meta?`<div class="meta">${esc(meta)}</div>`:''}${detail?`<div class="detail">${esc(detail)}</div>`:''}</div>`;
  }).join('');
  const errors=[status.state_error&&'调度状态读取失败（'+status.state_error+'）',
    status.audit_error&&'审计文件读取失败（'+status.audit_error+'）'].filter(Boolean);
  return `<div class="hbstatus"><h2>心跳运行记录 <span class="summary">已开启 ${esc(status.enabled_contacts||0)} 位 · 下次计划：${esc(next)}</span></h2><details data-detail="heartbeat-events"><summary>展开最近 ${events.length} 条执行记录</summary>
    ${errors.length?`<div class="warn">${esc(errors.join('；'))}</div>`:''}
    ${rows||'<div class="empty">暂无心跳事件记录；Butler 调度启动或下一轮触发后会显示过程。</div>'}</details></div>`;
}

function renderHeartbeatPane(){
  if(state.tab!=='heartbeat') return;
  const d = state.hdata, contact = d && (d.contacts||[]).find(c=>c.name===state.hContact);
  if(!d){ $('#pane').innerHTML = `<div class="empty">${esc(state.hError||'正在载入心跳配置…')}</div>`; return; }
  if(!contact){ $('#pane').innerHTML = `<div class="empty">${esc(state.hError||'请选择一个私聊联系人')}</div>`; return; }
  if(!state.hDraft){ $('#pane').innerHTML = `<div class="empty">${esc(state.hError||'正在载入角色 skill…')}</div>`; return; }
  const draft = state.hDraft, skills = state.hSkills;
  const roleSkills = skills.filter(isRoleSkill);
  const toolSkills = skills.filter(s=>!isRoleSkill(s)&&matchesQuery(s.name,s.description,s.category));
  const roleOptions = roleSkills.map(s=>`<option value="${esc(s.name)}" ${draft.role_skill===s.name?'selected':''}>${esc(s.name)}${s.category?' · '+esc(s.category):''}</option>`).join('');
  const selected = new Set(draft.allowed_skills||[]);
  const boxes = toolSkills.map(s=>{
    const checked = selected.has(s.name);
    return `<label class="hbskill"><input type="checkbox" data-hskill="${esc(s.name)}" ${checked?'checked':''}>
      <span><b>${esc(s.name)}</b>
        <div class="desc">${esc(s.description||s.category||'')}</div></span></label>`;
  }).join('');
  const interval = d.interval_minutes || {min:180,max:360};
  const savedPolicy = (d.policies||{})[contact.name] || {};
  $('#pane').innerHTML = `<div class="head"><h2>用户角色与心跳 · ${esc(contact.label||contact.name)}</h2>
    <div class="kv"><span>微信窗口 <b>${esc(contact.name)}</b></span><span>模型运行时 Profile <b>${esc(contact.profile)}</b></span>
      <span>心跳间隔 <b>${esc(interval.min)}–${esc(interval.max)} 分钟随机</b></span></div>
    <div class="hbactions"><button id="hb-trigger" class="wx" ${savedPolicy.role_skill&&!state.hTriggering?'':'disabled'}>${state.hTriggering?'提交中…':'立即触发此用户'}</button>
      <span class="hint">手动触发不受自动心跳开关限制，需先保存角色 Skill 配置。</span></div>
    ${state.hTriggerMessage?`<div class="hbnote">${esc(state.hTriggerMessage)}</div>`:''}</div>
    <div class="hbform">
      <div class="hbnote">普通私聊会使用下方角色和技能白名单，保存后下一条消息生效。心跳开启后，Butler 每次随机选择一名已开启用户，模型运行时 只返回建议，由 Butler 私聊发送。</div>
      <fieldset><legend>角色绑定</legend>
      <div class="hbrow"><label for="hb-role">角色 skill</label>
        <select id="hb-role"><option value="">请选择角色 skill</option>${roleOptions}</select>
        <span class="chip">角色 skill 会由 模型运行时 单独加入运行时白名单</span></div>
      </fieldset><fieldset><legend>允许调用的 Skill</legend>
      ${toolSkills.length?`<div class="hbskills">${boxes}</div>`:'<div class="empty">模型运行时 没有返回可用的工具 skills</div>'}
      </fieldset><fieldset><legend>自动心跳</legend><div class="hbrow"><label><input id="hb-enabled" type="checkbox" ${draft.heartbeat_enabled?'checked':''}> 为此用户开启心跳</label></div><div class="monitor-note">间隔 ${esc(interval.min)}–${esc(interval.max)} 分钟，每轮随机选择一位已开启用户。</div></fieldset>
      ${state.hError?`<div class="warn">${esc(state.hError)}</div>`:''}
      ${state.hSaved?`<div style="color:var(--ok);margin:8px 0">${esc(state.hSaved)}</div>`:''}
      <button id="hb-save" class="wx" ${skills.length?'':'disabled'}>保存配置</button>
    </div>${renderHeartbeatStatus()}`;
  $('#hb-enabled').onchange = e=>{ draft.heartbeat_enabled=e.target.checked; };
  $('#hb-role').onchange = e=>{
    draft.role_skill=e.target.value;
    draft.allowed_skills=draft.allowed_skills.filter(name=>name!==draft.role_skill);
    state.hSaved=''; renderHeartbeatPane();
  };
  $('#pane').querySelectorAll('[data-hskill]').forEach(box=>box.onchange=e=>{
    const name=e.target.dataset.hskill;
    const allowed=new Set(draft.allowed_skills);
    if(e.target.checked) allowed.add(name); else allowed.delete(name);
    draft.allowed_skills=[...allowed]; state.hSaved='';
  });
  $('#hb-save').onclick=saveHeartbeatPolicy;
  $('#hb-trigger').onclick=triggerHeartbeat;
}

async function triggerHeartbeat(){
  if(state.hTriggering||!state.hContact) return;
  state.hTriggering=true;
  state.hTriggerMessage='正在向 Butler 提交手动心跳…';
  renderHeartbeatPane();
  try{
    const result=await postJSON('/api/heartbeat-trigger',{contact:state.hContact});
    if(!result||!result.ok) throw new Error((result&&(result.error||result.detail))||'提交失败');
    state.hTriggerMessage='Butler 已接受请求；执行过程和建议会写入上方记录。';
    await new Promise(resolve=>setTimeout(resolve,400));
    try{
      state.hstatus=await apiGet('/api/heartbeat-status?limit=30');
      state.hStatusError='';
    }catch(e){ state.hStatusError=e.message||String(e); }
  }catch(e){ state.hTriggerMessage='触发失败：'+(e.message||e); }
  finally{
    state.hTriggering=false;
    renderHeartbeatPane();
  }
}

async function saveHeartbeatPolicy(){
  const draft=state.hDraft;
  state.hError=''; state.hSaved='';
  if(!draft.role_skill){ state.hError='请先选择角色 skill'; renderHeartbeatPane(); return; }
  try{
    const result=await postJSON('/api/heartbeat-config', {contact:state.hContact,
      role_skill:draft.role_skill, allowed_skills:draft.allowed_skills,
      heartbeat_enabled:draft.heartbeat_enabled});
    if(!result || !result.ok) throw new Error((result && (result.error||result.detail)) || '保存失败');
    state.hdata.policies[state.hContact]=result.policy;
    state.hSaved='已保存；普通消息与下一次心跳会读取此配置。';
  }catch(e){ state.hError='保存失败：'+(e.message||e); }
  renderHeartbeatNav(); renderHeartbeatPane();
}

/* ---------------- 收发队列 / 配置总览 ---------------- */
