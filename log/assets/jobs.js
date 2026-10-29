/* ---------------- 定时任务 ---------------- */
const JSTATE = { active:['运行中','jb-active'], paused:['已暂停','jb-paused'],
                 done:['已完成','jb-done'], error:['出错','jb-error'] };
const JTYPE = { 1:'type=1 单发', 2:'type=2 群发' };
const JMT = { 1:'新闻消息', 2:'问候消息', 3:'其他' };
const JSRC = { profile:'按 Profile 归属', script:'按 script 配置', prompt:'按 prompt 归属',
               'script-target':'脚本内置目标', 'script-profile':'脚本内置 Profile' };
const parseTs = s => { if(!s) return null; const t = Date.parse(s); return isNaN(t) ? null : t/1000; };
const jUidText = u => u.uid==='global' ? '群发 · 收件人由字典决定' : (u.uid_display||u.uid);

function jobCard(j){
  const st = JSTATE[j.ui_state] || ['?','jb-paused'];
  const err = j.last_delivery_error || j.last_error || '';
  const nxt = parseTs(j.next_run_at), lst = parseTs(j.last_run_at);
  const rows = [
    ['计划', esc(j.schedule||'-')],
    ['下次跑', nxt ? full(nxt) : '-'],
    ['上次跑', (lst ? full(lst) : '-') + (j.last_status ? ` · ${esc(j.last_status)}` : '')],
    ['投递到', esc(j.deliver||'-') + (JSRC[j.uid_source] ? ` <span style="color:var(--fg3)">（${esc(JSRC[j.uid_source])}）</span>` : '')],
    ['类型', (j.script ? 'script '+esc(j.script) : (j.no_agent ? 'no_agent' : 'agent'))
             + (j.repeat ? ` · ${esc(j.repeat)}` : '')],
  ];
  if(j.push_type || j.message_type){
    const bits = [];
    if(j.push_type) bits.push(JTYPE[j.push_type] || `type=${j.push_type}`);
    if(j.message_type) bits.push(`messageType=${j.message_type}（${JMT[j.message_type]||'?'}）`);
    if(j.scope==='global') bits.push('收件人按「用户分组」字典');
    rows.push(['推送', esc(bits.join(' · '))]);
  }
  if(err) rows.push(['错误', `<span class="err">${esc(err)}</span>`]);
  return `<div class="jcard ${j.ui_state}">
    <div class="t"><span class="nm">${esc(j.name)}</span><span class="jbadge ${st[1]}">${st[0]}</span></div>
    <div class="kv">${rows.map(r=>`<span class="l">${r[0]}</span><span class="v">${r[1]}</span>`).join('')}</div>
    ${j.prompt ? `<details><summary>prompt 摘要</summary><div class="pre">${esc(j.prompt)}</div></details>` : ''}
    <div class="queue-actions"><button class="discard" data-job-delete="${esc(j.job_id)}" data-job-profile="${esc(j.profile)}" ${!j.can_delete||state.jobDeleting?'disabled':''} title="${esc(j.can_delete?'删除后不再执行':j.delete_reason||'此任务由其他调度器管理，请到对应调度器删除')}">${state.jobDeleting===j.job_id?'删除中…':'删除'}</button></div>
  </div>`;
}

async function deleteJob(job){
  if(state.jobDeleting)return;
  if(!job.can_delete){state.jobError=job.delete_reason||'此任务请到对应调度器删除';renderJobs();return;}
  if(!confirm(`删除定时任务“${job.name}”？\n删除后不再执行，已经发送的消息不会撤回。`))return;
  state.jobDeleting=job.job_id;state.jobError='';state.jobMessage='';++state.jRequest;renderJobs();
  let deleted=false;
  try{
    const response=await fetch('/api/jobs/delete',{method:'POST',headers:{'Content-Type':'application/json','X-Wxbot-Job-Action':'1'},
      body:JSON.stringify({job_id:job.job_id,version:job.delete_version,acknowledge:true})});
    const data=await response.json();
    if(!response.ok||!data.ok)throw new Error(data.error||'删除失败，请刷新任务状态');
    state.jobMessage=`已删除定时任务“${job.name}”`;deleted=true;
  }catch(error){state.jobError=error.message||'删除请求失败，请刷新确认任务状态';}
  finally{state.jobDeleting='';}
  if(state.tab!=='jobs')return;
  if(deleted)await loadJobs();else renderJobs();
}

const jVisible = j => (state.jobShowDone || j.ui_state !== 'done')&&matchesQuery(j.name,j.uid,j.deliver,j.ui_state,j.last_error,j.job_id);
const jStats = jobs => ({
  count: jobs.length,
  active: jobs.filter(j=>j.ui_state==='active').length,
  paused: jobs.filter(j=>j.ui_state==='paused').length,
  error:  jobs.filter(j=>j.ui_state==='error').length,
  done:   jobs.filter(j=>j.ui_state==='done').length,
});

async function loadJobs(){
  const request=++state.jRequest;
  try{const data=await get('/api/jobs');if(request!==state.jRequest||state.tab!=='jobs')return;state.jobs=data;}
  catch(error){if(state.tab==='jobs'&&request===state.jRequest)$('#pane').innerHTML=`<div class="empty warn">${esc(error.message||error)}</div>`;return;}
  if(state.tab!=='jobs') return;
  renderJobsNav();
  renderJobs();
}

function renderJobsNav(){
  const d = state.jobs, el = $('#list');
  const all = jStats(d.users.flatMap(u=>u.jobs).filter(jVisible));
  const head = `<div class="user ${state.jobUid==='all'?'sel':''}" data-u="all">
      <div class="nm">全部归属</div>
      <div class="st"><span>归属 <b>${all.count}</b></span><span>活跃 ${all.active}</span>
        <span>暂停 ${all.paused}</span>${all.done?`<span>已完成 ${all.done}</span>`:''}
        ${d.count-all.count?`<span>隐藏已完成 ${d.count-all.count}</span>`:''}
        ${all.error?`<span class="warn">出错 ${all.error}</span>`:''}</div>
    </div>`;
  el.innerHTML = head + d.users.map(u=>{
    const st = jStats(u.jobs.filter(jVisible));
    const hidden = u.count - st.count;
    return `<div class="user ${state.jobUid===u.uid?'sel':''}" data-u="${esc(u.uid)}">
      <div class="nm">${esc(u.name)}</div>
      <div class="uid">${esc(jUidText(u))}</div>
      <div class="st"><span>归属 <b>${st.count}</b></span><span>活跃 ${st.active}</span>
        <span>暂停 ${st.paused}</span>${st.done?`<span>已完成 ${st.done}</span>`:''}
        ${hidden?`<span>隐藏已完成 ${hidden}</span>`:''}
        ${st.error?`<span class="warn">出错 ${st.error}</span>`:''}</div>
    </div>`;
  }).join('');
  el.querySelectorAll('.user').forEach(n=>n.onclick=()=>{
    state.jobUid = n.dataset.u;
    el.querySelectorAll('.user').forEach(x=>x.classList.toggle('sel', x.dataset.u===state.jobUid));
    renderJobs();
  });
}

function renderJobs(){
  const d = state.jobs;
  const feedback=`${state.jobError?`<p class="warn" role="alert">${esc(state.jobError)}</p>`:''}${state.jobMessage?`<p class="monitor-note" role="status">${esc(state.jobMessage)}</p>`:''}`;
  if(!d){ $('#pane').innerHTML=feedback+'<div class="empty">载入中…</div>'; return; }
  const secs = (state.jobUid==='all' ? d.users : d.users.filter(u=>u.uid===state.jobUid)).slice().sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'));
  if(!secs.length){ $('#pane').innerHTML=feedback+'<div class="empty">没有定时任务</div>'; return; }
  const hiddenIn = secs.reduce((a,u)=>a+u.jobs.filter(j=>!jVisible(j)).length, 0);
  if(secs.every(u=>!u.jobs.some(jVisible))){
    $('#pane').innerHTML = feedback+`<div class="empty">没有可显示的任务${
      hiddenIn?` —— ${hiddenIn} 个已完成已隐藏（点上方「显示已完成」查看）`:''}</div>`;
    return;
  }
  $('#pane').innerHTML = feedback+secs.map(u=>{
    const vjobs = u.jobs.filter(jVisible), st = jStats(vjobs);
    const hidden = u.jobs.length - vjobs.length;
    return `<div class="jsec">
      <h2>${esc(u.name)} <span class="uid">${esc(jUidText(u))}</span>
        <span class="k">共 ${st.count} 个</span><span class="k">活跃 ${st.active}</span>
        <span class="k">暂停 ${st.paused}</span>${st.done?`<span class="k">已完成 ${st.done}</span>`:''}
        ${hidden?`<span class="k">已完成 ${hidden}（已隐藏）</span>`:''}
        ${st.error?`<span class="k warn">出错 ${st.error}</span>`:''}</h2>
      ${vjobs.length ? `<div class="jgrid">${vjobs.map(jobCard).join('')}</div>`
        : '<div class="empty" style="padding:12px">该组的任务全部已完成（已隐藏）</div>'}
    </div>`;
  }).join('');
  $('#pane').querySelectorAll('[data-job-delete]').forEach(button=>button.onclick=()=>{
    const job=d.users.flatMap(u=>u.jobs).find(j=>j.job_id===button.dataset.jobDelete&&j.profile===button.dataset.jobProfile);
    if(job)deleteJob(job);
  });
}
